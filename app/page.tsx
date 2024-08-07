'use client'

import { useState, useCallback, useEffect } from "react";
import { ChangeEvent, DragEvent } from "react";
import axios from "axios";
import { io } from "socket.io-client";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");
  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

  useEffect(() => {
    const clientId = Date.now().toString();
    const socket = io("http://localhost:8000", {
      query: { clientId }
    });
  
    socket.on("connect", () => {
      console.log("Connected to WebSocket server");
    });
  
    socket.on("completed", () => {
      console.log("Received 'completed' event from WebSocket");
      setLoading(false);
      setProcessingStatus("Video processing completed");
      setDownloadUrl(`api/download/?path=videos/${file?.name.split('.')[0]}_output.mp4`);
    });
  
    return () => {
      socket.disconnect();
    };
  }, [file]);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      const selectedFile = event.target.files[0];
      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 50MB limit. Please choose a smaller file.");
        return;
      }
      setFile(selectedFile);
    }
  };

  const handleDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      const selectedFile = event.dataTransfer.files[0];
      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 50MB limit. Please choose a smaller file.");
        return;
      }
      setFile(selectedFile);
      event.dataTransfer.clearData();
    }
  }, []);

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  const handleUpload = async () => {
    if (!file) return;

    setLoading(true);
    setProcessingStatus("Uploading...");
    setDownloadUrl("");
    const VIDDYSCRIBE_API_KEY = "viddysc-8f6f7d0195efd6a0e11581e0caa26c140347392dee1a18698c7b1dd1fac46cd6"

    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await axios.post("api/create_video", formData, {
        headers: {
          'Authorization': `Bearer ${VIDDYSCRIBE_API_KEY}`,
          'client_id': Date.now().toString()
        },
        timeout: 1200000 // 20 minutes
      });
      if (response.data.status === "processing") {
        setProcessingStatus("Processing video...");
      } else {
        setLoading(false);
        console.error("Unexpected response from server");
      }
    } catch (error) {
      console.error("Failed to start video processing", error);
      setLoading(false);
      setProcessingStatus("Error: Failed to start processing");
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      <p className="text-4xl text-zinc-100 font-bold text-center mb-8">ViddyScribe</p>
      <div 
        className={`p-16 border-2 transition-all border-white/50 border-dashed rounded-lg text-center cursor-pointer text-zinc-100/70 ${file ? 'bg-zinc-700' : 'hover:bg-zinc-800'}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => {
            const fileInput = document.getElementById('fileInput');
            if (fileInput) {
                fileInput.click();
            }
        }}
      >
        <input 
          id="fileInput"
          type="file" 
          onChange={handleFileChange} 
          className="hidden" 
        />
        <p>
          {file ? <><b>Selected video</b> {file.name}</> : "Drag & Drop your file here or Tap to choose file"}
        </p>
      </div>
      <button 
        onClick={handleUpload} 
        className="mt-4 btn btn-upload" 
        disabled={loading}
      >
        {loading ? "Processing..." : "Upload and Generate"}
      </button>
      {processingStatus && <p className="text-zinc-100">{processingStatus}</p>}
      {downloadUrl && (
        <a 
          href={downloadUrl} 
          download="output_video.mp4" 
          className="mt-4 btn btn-download"
        >
          Download Video
        </a>
      )}
    </main>
  );
}