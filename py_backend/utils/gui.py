#todo: this is light weight implement real logic 
# utils/gui.py
import sys
import os
import threading
import time
from pathlib import Path
from typing import Optional
from PyQt5 import QtWidgets, QtCore, QtGui

# must import NPCAgent from your ai_core package
from ai_core import NPCAgent

# simple background trainer stub (non-blocking)
def _background_train_from_text(agent: NPCAgent, text: str, timesteps: int = 256):
    """
    Lightweight hook: put text into memory and perform a small 'learning' step.
    This is intentionally conservative: real RL training should run in separate process.
    """
    # remember the file text as a learning example
    agent.memory.remember({'type': 'file_training', 'tags': ['file'], 'payload': {'text_sample': text[:2048]}}, tags=['training'])
    # optionally perform a personality update from the content novelty
    novelty = agent.memory.novelty_score(text[:512])
    agent.personality.apply_update([0.0, 0.0, 0.0, 0.0, 0.02 * novelty, 0.01 * novelty, 0.0, -0.01 * novelty], lr=0.05)
    # also add a tiny emotion bump for 'joy' if novel
    agent.emotion.add('joy', 0.01 * novelty)
    # fallback small simulated training loop (do not call heavy RL here)
    # If user wants heavy training, they should call rl.train.py separately
    return True

class DragDropTextEdit(QtWidgets.QTextEdit):
    fileDropped = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setReadOnly(True)
        self.setPlaceholderText("Drop text files here or type messages below...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # handle file(s)
        md = event.mimeData()
        if md.hasUrls():
            urls = md.urls()
            for u in urls:
                path = u.toLocalFile()
                if not path:
                    continue
                try:
                    self.fileDropped.emit(path)
                except Exception:
                    pass
        elif md.hasText():
            txt = md.text()
            tmp = Path("data/dragdrop_tmp.txt")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(txt, encoding="utf-8")
            self.fileDropped.emit(str(tmp))
        event.acceptProposedAction()

class AgentGUI:
    """
    PyQt5 GUI for interacting with NPCAgent.
    - Left: chat input + conversation history
    - Right: agent thoughts / last actions / emotion snapshot
    - Drag & drop files -> agent.memory.remember(...) and background training hook
    """
    def __init__(self, agent: NPCAgent):
        self.agent = agent
        self.app = QtWidgets.QApplication(sys.argv)
        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle("DivineWorld - Agent GUI")
        self.window.setMinimumSize(900, 600)
        self._build_ui()
        # background thread flag
        self._stop = False
        # start periodic poller for agent thoughts
        self._poll_thread = threading.Thread(target=self._poll_agent_loop, daemon=True)
        self._poll_thread.start()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self.window)

        # Left column: conversation
        left = QtWidgets.QVBoxLayout()
        self.conv_view = QtWidgets.QTextEdit()
        self.conv_view.setReadOnly(True)
        self.conv_view.setPlaceholderText("Conversation history")
        left.addWidget(self.conv_view)

        # chat input
        chat_row = QtWidgets.QHBoxLayout()
        self.chat_input = QtWidgets.QLineEdit()
        self.chat_input.setPlaceholderText("Type a message and press Send")
        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.clicked.connect(self._on_send)
        chat_row.addWidget(self.chat_input)
        chat_row.addWidget(self.send_btn)
        left.addLayout(chat_row)

        # Drag & Drop area
        self.drop_area = DragDropTextEdit()
        self.drop_area.fileDropped.connect(self._handle_dropped_file)
        left.addWidget(QtWidgets.QLabel("Drag & drop a text/JSON file to teach the agent:"))
        left.addWidget(self.drop_area)

        # Right column: agent thoughts / actions
        right = QtWidgets.QVBoxLayout()
        right.addWidget(QtWidgets.QLabel("Agent Thoughts / Actions"))
        self.thoughts = QtWidgets.QTextEdit()
        self.thoughts.setReadOnly(True)
        right.addWidget(self.thoughts)
        right.addWidget(QtWidgets.QLabel("Agent Emotions / Personality"))
        self.status = QtWidgets.QTextEdit()
        self.status.setReadOnly(True)
        right.addWidget(self.status)

        layout.addLayout(left, 2)
        layout.addLayout(right, 1)

        self.window.setLayout(layout)

    def _on_send(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        # append to conversation view
        self.conv_view.append(f"<b>You:</b> {QtWidgets.QTextDocument().toPlainText() if False else text}")
        # store in agent memory and optionally send to planner/brain
        ev = {'type': 'human_chat', 'tags': ['human_chat'], 'payload': {'text': text}}
        self.agent.memory.remember(ev, tags=['chat'])
        # simple reply logic (use agent.brain or oracle later)
        reply = f"I heard: {text[:200]}"
        self.conv_view.append(f"<b>Agent:</b> {reply}")
        self.agent.memory.remember({'type': 'chat_reply', 'tags': ['chat'], 'payload': {'text': reply}}, tags=['chat'])
        self.chat_input.clear()

    def _handle_dropped_file(self, path: str):
        # read file content (attempt binary-safe detection)
        try:
            p = Path(path)
            if not p.exists():
                self.drop_area.append(f"File not found: {path}")
                return
            if p.stat().st_size > 10 * 1024 * 1024:
                # too large
                self.drop_area.append(f"File too large (>10MB): {p.name}")
                return
            # try read text
            text = None
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                # fallback to latin-1
                text = p.read_text(encoding="latin-1")
        except Exception as e:
            self.drop_area.append(f"Failed to read {path}: {e}")
            return

        # show small snippet
        snippet = (text[:2000] + "...") if len(text) > 2000 else text
        self.drop_area.append(f"Loaded {p.name} ({len(text)} bytes). Snippet:\n{snippet}")

        # store in memory and trigger background training hook
        self.drop_area.append("Queuing background training from file...")
        t = threading.Thread(target=self._train_from_file_thread, args=(text, p.name), daemon=True)
        t.start()

    def _train_from_file_thread(self, text: str, name: str):
        try:
            _background_train_from_text(self.agent, text)
            # append to GUI logs: do inside GUI thread
            def gui_update():
                self.thoughts.append(f"[TRAIN] Ingested file '{name}' -> memory_size={len(self.agent.memory.events)}")
            QtCore.QMetaObject.invokeMethod(self.window, gui_update, QtCore.Qt.QueuedConnection)
        except Exception as e:
            def gui_error():
                self.thoughts.append(f"[TRAIN-ERR] {e}")
            QtCore.QMetaObject.invokeMethod(self.window, gui_error, QtCore.Qt.QueuedConnection)

    def _poll_agent_loop(self):
        """
        Poll agent periodically for thoughts/status and update GUI.
        Runs in background thread to keep UI responsive.
        """
        while True:
            try:
                thought = f"Last emotions: {self.agent.emotion.snapshot()}\nPersonality: {self.agent.personality.as_array().tolist()}"
                last_mem = None
                try:
                    last_mem = list(self.agent.memory.events)[-1]
                except Exception:
                    last_mem = None
                def gui_update():
                    self.status.setPlainText(thought)
                    if last_mem:
                        self.thoughts.append(f"[MEM] {last_mem['text'][:200]}")
                QtCore.QMetaObject.invokeMethod(self.window, gui_update, QtCore.Qt.QueuedConnection)
            except Exception:
                pass
            time.sleep(2.0)

    def run(self):
        self.window.show()
        sys.exit(self.app.exec_())
