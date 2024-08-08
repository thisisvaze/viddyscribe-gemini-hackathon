'use client'

import { useState, useCallback, useEffect, useRef } from "react";
import { ChangeEvent, DragEvent } from "react";
import axios from "axios";
import Image from 'next/image';

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");
  const MAX_FILE_SIZE = 7 * 1024 * 1024; // 50MB
  const [addBgMusic, setAddBgMusic] = useState(false);
  const clientIdRef = useRef(Date.now().toString()); // Generate client ID once and store in ref

  useEffect(() => {
    const isProd = process.env.NODE_ENV === 'production';
    const wsUrl = 'ws://localhost:8001/ws';
    const socket = new WebSocket(`${wsUrl}?client_id=${clientIdRef.current}`);

    socket.onopen = () => {
      console.log("Connected to WebSocket server");
    };

    socket.onmessage = (event) => {
      console.log("Received message from WebSocket:", event.data);
      const message = JSON.parse(event.data);
      if (message.status === "completed") {
        console.log("Received 'completed' event from WebSocket");
        setLoading(false);
        setProcessingStatus("Video processing completed");
        setDownloadUrl(`api/download/?path=${message.output_path}`);
      }
    };

    socket.onclose = () => {
      console.log("Disconnected from WebSocket server");
    };

    return () => {
      socket.close();
    };
  }, [file]);

  const handleCancel = async () => {
    if (confirm("Are you sure you want to cancel? You will have to start the request again.")) {
      try {
        window.location.reload();
      } catch (error) {
        console.error("Failed to cancel video processing", error);
        alert("Failed to cancel video processing");
      }
    }
  };


  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      const selectedFile = event.target.files[0];
      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 7MB limit. Please choose a smaller file.");
        return;
      }

      const video = document.createElement('video');
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        window.URL.revokeObjectURL(video.src);
        if (video.duration > 120) {
          alert("Video duration exceeds the 2 minutes limit. Please choose a shorter video.");
          return;
        }
        setFile(selectedFile);
      };
      video.src = URL.createObjectURL(selectedFile);
    }
  };

  const handleDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      const selectedFile = event.dataTransfer.files[0];
      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 7MB limit. Please choose a smaller file.");
        return;
      }

      const video = document.createElement('video');
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        window.URL.revokeObjectURL(video.src);
        if (video.duration > 120) {
          alert("Video duration exceeds the 2 minutes limit. Please choose a shorter video.");
          return;
        }
        setFile(selectedFile);
        event.dataTransfer.clearData();
      };
      video.src = URL.createObjectURL(selectedFile);
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
    const VIDDYSCRIBE_API_KEY = process.env.VIDDYSCRIBE_API_KEY;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("add_bg_music", addBgMusic.toString());
    formData.append("client_id", clientIdRef.current);  // Add client_id to form data

    // Log form data for debugging
    console.log("Form Data:", formData);
    console.log("Headers:", {
      'Authorization': `Bearer ${VIDDYSCRIBE_API_KEY}`,
      'Content-Type': 'multipart/form-data'
    });

    try {
      const response = await axios.post("/api/create_video", formData, {
        headers: {
          'Authorization': `Bearer ${VIDDYSCRIBE_API_KEY}`,
          'Content-Type': 'multipart/form-data'
        },
        timeout: 1200000 // 20 minutes
      });

      if (response.status === 200) {
        setProcessingStatus("Processing video... This may take up to 5 minutes.");
      } else {
        throw new Error("Unexpected response status");
      }
    } catch (error) {
      console.error("Failed to start video processing", error);
      setLoading(false);
      setProcessingStatus("Error: Failed to start processing");
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-start gap-12 lg:gap-24  px-4 lg:px-24 pt-6 lg:pt-12 pb-12 lg:pb-24">
      <div className="flex flex-col items-center">
        <Image src="/viddy_logo.png" alt="ViddyScribe Logo" width={90} height={90} className="lg:h-32 lg:w-32 h-12 w-12" />
        <p className="text-4xl text-zinc-100 font-bold text-center mt-8">ViddyScribe</p>
        <p className="text-sm lg:text-lg text-zinc-100/50  text-center mt-3">Add Audio description to videos with AI</p>
      </div>
      <div>
        <div
          className={`p-8 lg:p-20 border-2 transition-all border-white/50 border-dashed rounded-xl text-center cursor-pointer text-zinc-100/70 ${file ? 'bg-zinc-700 hover:bg-zinc-800 border-none' : 'bg-zinc-900 hover:bg-zinc-800'} ${loading ? 'opacity-70' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onClick={() => {
            if (!loading) {
              const fileInput = document.getElementById('fileInput');
              if (fileInput) {
                fileInput.click();
              }
            }
          }}
        >
          <input
            id="fileInput"
            type="file"
            onChange={handleFileChange}
            className="hidden"
            disabled={loading}
          />
          <p className=" lg:text-xl">
            {file ? <><b>Selected video</b> {file.name}</> : "Drag & Drop your file here or Tap to choose file"}
          </p>
          <p className=" text-zinc-100 text-center text-sm lg:text-md  mt-3">Currently supports only .mp4 files &lt; 7 MB and duration &lt; 2 minutes.</p>
        </div>
        <div className="items-center justify-center flex mt-4">
          <label className="text-zinc-100 checkbox-container">
            <input
              type="checkbox"
              checked={addBgMusic}
              onChange={(e) => setAddBgMusic(e.target.checked)}
              className="mr-2 checkbox"
              disabled={loading}
            />
            AI generated background audio for descriptions
            <span className="text-2xl ml-2"> 🥁 </span>
          </label>
        </div>
      </div>
      <div>
        {processingStatus && (
          <p className={`text-zinc-100/70 font-bold text-sm ${processingStatus !== "Video processing completed" ? "blink-animation" : ""}`}>
            {processingStatus}
          </p>
        )}
        <button
          onClick={handleUpload}
          className="mt-4 btn btn-upload"
          disabled={loading}
        >
          {loading ? "Processing..." : "Upload and Generate"}
        </button>
        {loading && (
          <p
            className="mt-2 text-zinc-100/50 underline cursor-pointer"
            onClick={handleCancel}
          >
            Cancel
          </p>
        )}
        {downloadUrl && file && (
          <a
            href={downloadUrl}
            download={`${file?.name.replace(/\.[^/.]+$/, "")}_with_audio_desc${file?.name.match(/\.[^/.]+$/)?.[0]}`} // Append _with_audio_desc to the original filename
            className="mt-4 btn btn-download"
          >
            Download Video
          </a>
        )}
      </div>

    </main>
  );
}