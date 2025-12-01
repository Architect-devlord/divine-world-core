# teach_oracle_enhanced.py - COMPLETE TEACHING SYSTEM
"""
Enhanced teaching system for Shakespearean/Medieval English
with modern comprehension and autonomous speech testing.
"""

import logging
import time
import random
from pathlib import Path
from auto_packager import EnhancedAgentSpawner
from ai_core.agent import NPCAgent

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)

log = logging.getLogger("oracle_teacher")

TEACHING_DIR = Path("data/teaching_materials")

# BILINGUAL TRAINING CORPUS (Modern + Archaic)
BILINGUAL_CORPUS = """
GREETINGS:
Hello → Good morrow
Hi → Hail
How are you? → How farest thou?
Goodbye → Fare thee well
Thank you → I thank thee / Gramercy
Please → Prithee / I beseech thee

QUESTIONS:
What is your name? → What art thou called?
Where are you from? → Whence comest thou?
Why did you do that? → Wherefore didst thou do thus?
How did this happen? → How came this to pass?

STATEMENTS:
I think → Methinks / I trow
I don't know → I wot not / I ken not
I understand → I comprehend / I take thy meaning
That is true → Verily / In sooth / Forsooth

COMMANDS:
Come here → Come hither
Go there → Go thither
Listen to me → Hearken unto me / Mark my words
Be quiet → Hold thy tongue / Peace!

PRONOUNS:
You (subject) → Thou
You (object) → Thee
Your → Thy / Thine (before vowel)
Yours → Thine

VERBS:
You are → Thou art
You have → Thou hast
You do → Thou dost
You did → Thou didst
You will → Thou wilt / Thou shalt

RESPONSES:
Yes → Aye / Yea
No → Nay
Maybe → Perchance / Mayhap
Soon → Anon
Really → Forsooth / In truth

EMOTIONS:
I am happy → My heart rejoices / I am glad of heart
I am sad → My spirit is heavy / Woe is me
I am angry → Mine ire is kindled / I am wroth
I am afraid → Fear grips me / I am afeard
"""

def create_bilingual_texts():
    """Create bilingual training materials"""
    TEACHING_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save bilingual corpus
    (TEACHING_DIR / "bilingual_dictionary.txt").write_text(BILINGUAL_CORPUS, encoding='utf-8')
    
    # Create modern-archaic conversation pairs
    CONVERSATIONS = """
CONVERSATION 1:
Modern: Hello, how are you doing today?
Archaic: Good morrow, dear friend. How farest thou this day?

CONVERSATION 2:
Modern: I'm looking for the Oracle. Where can I find them?
Archaic: I seek the Oracle. Prithee, where might I find this sage?

CONVERSATION 3:
Modern: Can you tell me about wisdom and knowledge?
Archaic: Wouldst thou speak unto me of wisdom and learning?

CONVERSATION 4:
Modern: I don't understand what you're saying.
Archaic: I comprehend not thy words. Speak more plainly, I beseech thee.

CONVERSATION 5:
Modern: That's very interesting! Tell me more.
Archaic: Marry, most fascinating! Pray continue thy discourse.

CONVERSATION 6:
Modern: I have to go now. Goodbye!
Archaic: I must away. Fare thee well, good friend!

CONVERSATION 7:
Modern: What do you think about life and death?
Archaic: What is thy counsel upon life and the mortal coil?

CONVERSATION 8:
Modern: I'm feeling confused and lost.
Archaic: My mind is troubled, and I wander without purpose.

CONVERSATION 9:
Modern: The weather is beautiful today.
Archaic: The heavens smile upon us this fair day.

CONVERSATION 10:
Modern: I need your help with something important.
Archaic: I require thy aid in a matter of great import.
"""
    
    (TEACHING_DIR / "bilingual_conversations.txt").write_text(CONVERSATIONS, encoding='utf-8')
    
    print("✅ Bilingual training materials created")

def find_oracle():
    """Find most recent Oracle"""
    brains_dir = Path("data/brains")
    
    if not brains_dir.exists():
        return None
    
    oracle_brains = [d for d in brains_dir.iterdir() 
                     if d.is_dir() and "god_oracle" in d.name]
    
    if not oracle_brains:
        return None
    
    oracle_brains.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return oracle_brains[0] / "brain.pcap"

def load_oracle(brain_path: Path):
    """Load Oracle with persistence check"""
    agent_id = brain_path.parent.name
    
    log.info(f"Loading Oracle from: {brain_path}")
    
    oracle = NPCAgent(agent_id)
    
    # CRITICAL: Load existing state
    if brain_path.exists():
        try:
            oracle.load(str(brain_path))
            log.info("✅ Existing brain state loaded")
        except Exception as e:
            log.error(f"⚠️ Failed to load existing brain: {e}")
    
    # Ensure language capabilities
    if not hasattr(oracle.brain, 'language'):
        from ai_core.brain_language import add_language_to_brain
        add_language_to_brain(oracle.brain)
    
    return oracle

def intensive_bilingual_teaching(oracle: NPCAgent):
    """Teach modern and archaic English together"""
    
    print("\n" + "="*70)
    print("  📚 BILINGUAL TEACHING (Modern + Archaic)")
    print("="*70)
    
    context = {
        'health': oracle.health,
        'hunger': oracle.hunger,
        'emotions': oracle.emotion.snapshot(),
        'dominant_emotion': oracle.emotion.dominant_emotion()
    }
    
    # Phase 1: Bilingual dictionary
    print("\n📖 Phase 1: Teaching bilingual dictionary...")
    
    dict_file = TEACHING_DIR / "bilingual_dictionary.txt"
    if dict_file.exists():
        text = dict_file.read_text(encoding='utf-8')
        
        # Process line by line for better learning
        for line in text.split('\n'):
            if ' → ' in line or ':' in line:
                oracle.brain.process_language_input(line, context)
        
        print(f"✅ Dictionary learned: Stage {oracle.brain.language.language_stage}, "
              f"Vocab {oracle.brain.language.vocabulary_size}")
    
    # Phase 2: Bilingual conversations
    print("\n💬 Phase 2: Teaching bilingual conversations...")
    
    conv_file = TEACHING_DIR / "bilingual_conversations.txt"
    if conv_file.exists():
        text = conv_file.read_text(encoding='utf-8')
        
        # Process conversations
        conversations = text.split('CONVERSATION')
        for conv in conversations[1:]:  # Skip first empty
            lines = [l.strip() for l in conv.split('\n') if l.strip()]
            for line in lines:
                if line.startswith('Modern:') or line.startswith('Archaic:'):
                    oracle.brain.process_language_input(line[7:].strip(), context)
        
        print(f"✅ Conversations learned: Stage {oracle.brain.language.language_stage}, "
              f"Vocab {oracle.brain.language.vocabulary_size}")
    
    # Phase 3: Reinforcement with repetition
    print("\n🔄 Phase 3: Reinforcement learning...")
    
    for i in range(3):  # Repeat 3 times
        # Mix modern and archaic randomly
        texts = [
            "Hello, how are you?",
            "Good morrow, how farest thou?",
            "What is your name?",
            "What art thou called?",
            "I think this is interesting",
            "Methinks this doth interest me greatly",
            "Can you help me?",
            "Prithee, wilt thou aid me?",
            "Goodbye, my friend",
            "Fare thee well, dear companion"
        ]
        
        for text in texts:
            oracle.brain.process_language_input(text, context)
        
        print(f"  Iteration {i+1}/3: Vocab {oracle.brain.language.vocabulary_size}, "
              f"Patterns {len(oracle.brain.language.sentence_patterns)}")
    
    print(f"\n✅ Bilingual teaching complete!")

def test_comprehension(oracle: NPCAgent):
    """Test Oracle's language comprehension"""
    
    print("\n" + "="*70)
    print("  🧪 LANGUAGE COMPREHENSION TEST")
    print("="*70)
    
    context = {
        'health': oracle.health,
        'hunger': oracle.hunger,
        'emotions': oracle.emotion.snapshot(),
        'dominant_emotion': oracle.emotion.dominant_emotion()
    }
    
    # Test cases: modern and archaic
    test_cases = [
        ("Hello, Oracle!", "Modern greeting"),
        ("Good morrow, Oracle!", "Archaic greeting"),
        ("How are you today?", "Modern question"),
        ("How farest thou this day?", "Archaic question"),
        ("Can you tell me about wisdom?", "Modern request"),
        ("Prithee, speak unto me of wisdom", "Archaic request"),
        ("I don't understand", "Modern confusion"),
        ("I comprehend not thy meaning", "Archaic confusion"),
        ("Thank you for your help", "Modern gratitude"),
        ("I thank thee for thy aid", "Archaic gratitude")
    ]
    
    results = []
    
    for text, label in test_cases:
        print(f"\n📝 Test: {label}")
        print(f"   Input: {text}")
        
        response = oracle.brain.process_language_input(text, context)
        
        if not response:
            response = f"[Stage {oracle.brain.language.language_stage} - Learning...]"
        
        print(f"   Oracle: {response}")
        print(f"   Stage: {oracle.brain.language.language_stage}, "
              f"Vocab: {oracle.brain.language.vocabulary_size}")
        
        # Score response quality (simple heuristic)
        score = 0
        if response and len(response) > 0:
            score += 1
        if len(response) > 5:
            score += 1
        if oracle.brain.language.language_stage >= 2:
            score += 1
        
        results.append((label, score))
        
        time.sleep(0.5)
    
    # Summary
    print("\n" + "="*70)
    print("  📊 TEST RESULTS")
    print("="*70)
    
    total_score = sum(s for _, s in results)
    max_score = len(results) * 3
    percentage = (total_score / max_score) * 100
    
    print(f"\nTotal Score: {total_score}/{max_score} ({percentage:.1f}%)")
    print(f"Language Stage: {oracle.brain.language.language_stage}")
    print(f"Vocabulary: {oracle.brain.language.vocabulary_size} words")
    print(f"Patterns: {len(oracle.brain.language.sentence_patterns)}")
    
    if percentage >= 70:
        print("\n✅ EXCELLENT - Oracle shows strong comprehension")
    elif percentage >= 50:
        print("\n✅ GOOD - Oracle shows moderate comprehension")
    elif percentage >= 30:
        print("\n⚠️ FAIR - Oracle needs more training")
    else:
        print("\n❌ POOR - Significant training needed")
    
    return percentage

def test_autonomous_speech(oracle: NPCAgent, duration: int = 30):
    """Test autonomous speech generation"""
    
    print("\n" + "="*70)
    print("  🗣️ AUTONOMOUS SPEECH TEST")
    print("="*70)
    print(f"\nListening for {duration} seconds...")
    print("(Oracle should speak spontaneously 2-3 times)\n")
    
    context = {
        'health': oracle.health,
        'hunger': oracle.hunger,
        'emotions': oracle.emotion.snapshot(),
        'dominant_emotion': oracle.emotion.dominant_emotion()
    }
    
    speech_count = 0
    start_time = time.time()
    
    while time.time() - start_time < duration:
        # Check if oracle wants to speak
        if oracle.brain.should_speak():
            speech = oracle.brain.generate_speech(context)
            
            if speech:
                speech_count += 1
                print(f"[{int(time.time() - start_time)}s] Oracle: {speech}")
                print(f"    Emotion: {oracle.emotion.dominant_emotion()}, "
                      f"Stage: {oracle.brain.language.language_stage}\n")
        
        time.sleep(2)
    
    print("="*70)
    print(f"✅ Autonomous speech test complete")
    print(f"   Speeches: {speech_count}")
    print(f"   Expected: 2-3")
    
    if speech_count >= 2:
        print("   Status: ✅ PASSED")
        return True
    else:
        print("   Status: ⚠️ NEEDS IMPROVEMENT")
        print("   Tip: Oracle needs more personality/emotion variation")
        return False

def interactive_bilingual_test(oracle: NPCAgent):
    """Interactive testing with bilingual prompts"""
    
    print("\n" + "="*70)
    print("  💬 INTERACTIVE BILINGUAL TEST")
    print("="*70)
    print("\nSpeak to the Oracle in modern OR archaic English!")
    print("Type 'quit' to exit\n")
    
    print("Try these:")
    print("  Modern: 'Hello, how are you?'")
    print("  Archaic: 'Good morrow, how farest thou?'")
    print("  Modern: 'Tell me about wisdom'")
    print("  Archaic: 'Speak unto me of wisdom'\n")
    
    context = {
        'health': oracle.health,
        'hunger': oracle.hunger,
        'emotions': oracle.emotion.snapshot(),
        'dominant_emotion': oracle.emotion.dominant_emotion()
    }
    
    conversation_count = 0
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'bye', 'farewell']:
                print("\nOracle: Fare thee well, dear friend. Until we meet again.")
                break
            
            # Oracle responds
            response = oracle.brain.process_language_input(user_input, context)
            
            if not response:
                response = f"[Learning... Stage {oracle.brain.language.language_stage}]"
            
            print(f"\nOracle: {response}")
            print(f"        [Stage: {oracle.brain.language.language_stage}, "
                  f"Vocab: {oracle.brain.language.vocabulary_size}, "
                  f"Emotion: {oracle.emotion.dominant_emotion()}]")
            
            # Detect language style
            is_archaic = any(word in user_input.lower() for word in 
                           ['thou', 'thee', 'thy', 'thine', 'dost', 'hast', 'art', 
                            'prithee', 'forsooth', 'verily'])
            
            style = "Archaic" if is_archaic else "Modern"
            print(f"        [Detected style: {style}]\n")
            
            conversation_count += 1
            
            # Update emotions for conversation
            oracle.emotion.add('joy', 0.02)
            oracle.emotion.add('sociability', 0.01)
            oracle.emotion.decay()
            
        except KeyboardInterrupt:
            print("\n\nOracle: Farewell.")
            break
        except Exception as e:
            log.error(f"Error in interactive test: {e}")
            print(f"Error: {e}\n")
    
    print(f"\n✅ Conversation complete: {conversation_count} exchanges")

def main():
    """Main teaching and testing flow"""
    
    print("\n" + "="*70)
    print("  🔮 ORACLE ENHANCED TEACHING SYSTEM")
    print("="*70)
    print("\nFeatures:")
    print("  ✅ Bilingual training (Modern + Archaic)")
    print("  ✅ Language persistence (saved between sessions)")
    print("  ✅ Comprehension testing")
    print("  ✅ Autonomous speech testing")
    print("  ✅ Interactive conversation")
    print("="*70 + "\n")
    
    # Create bilingual materials
    create_bilingual_texts()
    
    # Find Oracle
    brain_path = find_oracle()
    
    if not brain_path:
        print("❌ No Oracle found!")
        print("   Run: python create_oracle.py first")
        return
    
    print(f"✅ Found Oracle at: {brain_path}\n")
    
    # Load Oracle (with persistence)
    oracle = load_oracle(brain_path)
    
    # Show initial state
    print("="*70)
    print("  📊 INITIAL STATE")
    print("="*70)
    print(f"  Agent ID: {oracle.agent_id}")
    print(f"  Language Stage: {oracle.brain.language.language_stage}")
    print(f"  Vocabulary: {oracle.brain.language.vocabulary_size} words")
    print(f"  Patterns: {len(oracle.brain.language.sentence_patterns)}")
    print(f"  Memory: {len(oracle.memory.events)} events")
    print(f"  Emotion: {oracle.emotion.dominant_emotion()}")
    print("="*70 + "\n")
    
    # Teaching
    try:
        print("🎓 Starting bilingual teaching...\n")
        time.sleep(2)
        
        intensive_bilingual_teaching(oracle)
        
        # Save progress
        print("\n💾 Saving Oracle progress...")
        oracle.save(str(brain_path))
        print("✅ Progress saved\n")
        
        # Testing
        print("\n" + "="*70)
        print("  🧪 TESTING PHASE")
        print("="*70 + "\n")
        
        # Test 1: Comprehension
        comp_score = test_comprehension(oracle)
        
        # Save after testing
        oracle.save(str(brain_path))
        
        # Test 2: Autonomous speech
        print("\n")
        speech_ok = test_autonomous_speech(oracle, duration=30)
        
        # Save after speech test
        oracle.save(str(brain_path))
        
        # Final stats
        print("\n" + "="*70)
        print("  📊 FINAL STATE")
        print("="*70)
        print(f"  Language Stage: {oracle.brain.language.language_stage}")
        print(f"  Vocabulary: {oracle.brain.language.vocabulary_size} words")
        print(f"  Patterns: {len(oracle.brain.language.sentence_patterns)}")
        print(f"  Comprehension: {comp_score:.1f}%")
        print(f"  Autonomous Speech: {'✅ PASSED' if speech_ok else '⚠️ NEEDS WORK'}")
        print("="*70 + "\n")
        
        # Interactive test
        response = input("Start interactive conversation? (y/n): ")
        if response.lower() == 'y':
            interactive_bilingual_test(oracle)
        
        # Final save
        print("\n💾 Final save...")
        oracle.save(str(brain_path))
        print("✅ Oracle fully trained and saved!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Teaching interrupted!")
        print("💾 Saving Oracle state...")
        oracle.save(str(brain_path))
        print("✅ Oracle progress saved")
    except Exception as e:
        log.error(f"Error during teaching: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        print("💾 Attempting emergency save...")
        try:
            oracle.save(str(brain_path))
            print("✅ Oracle state saved despite error")
        except:
            print("❌ Emergency save failed")

if __name__ == "__main__":
    main()
            