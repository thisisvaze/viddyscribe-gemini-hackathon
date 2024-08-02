'use client'
import { useState, useCallback } from "react";
import { ChangeEvent, DragEvent } from "react";
import axios from "axios"; // Import Axios

export default function Home() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState(""); // Add state for download URL

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files[0]);
  };

  const handleDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      setFile(event.dataTransfer.files[0]);
      event.dataTransfer.clearData();
    }
  }, []);

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  const handleUpload = async () => {
    if (!file) return;

    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);

    const controller = new AbortController();
    const signal = controller.signal;

    // Set a timeout for the Axios request
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 seconds timeout

    try {
      const response = await axios.post("/api/generate", formData, {
        signal: signal,
        timeout: 60000, // 60 seconds timeout
      });

      clearTimeout(timeoutId); // Clear the timeout if the request completes in time

      setLoading(false);

      if (response.status === 200) {
        const outputPath = response.data.output_path;
        const url = `/api/download?path=${encodeURIComponent(outputPath)}`;
        setDownloadUrl(url); // Set the download URL
      } else {
        console.error("Failed to generate video");
      }
    } catch (error) {
      if (axios.isCancel(error)) {
        console.error("Request timed out");
      } else {
        console.error("Failed to generate video", error);
      }
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      <p className="text-4xl text-zinc-100 font-bold text-center mb-8">ViddyScribe</p>
      <div 
        className={`p-16 border-2 transition-all border-white/50 border-dashed rounded-lg text-center cursor-pointer text-zinc-100/70 ${file ? 'bg-zinc-700' : 'hover:bg-zinc-800'}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => document.getElementById('fileInput').click()}
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
        {loading ? "Creating..." : "Upload and Generate"}
      </button>
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