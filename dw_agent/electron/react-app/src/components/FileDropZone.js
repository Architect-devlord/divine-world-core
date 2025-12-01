import React from "react";

function FileDropZone({ onFileSend }) {
  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) {
      const type = file.type.split("/")[0];
      onFileSend(file, type);
    }
  };

  return (
    <div
      className="file-dropzone"
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      Drop files here to send to agent
    </div>
  );
}

export default FileDropZone;
