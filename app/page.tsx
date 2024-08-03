'use client'
import { useState, useCallback, useEffect } from "react";
import { ChangeEvent, DragEvent } from "react";
import axios from "axios";

export default function Home() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");

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
    setProcessingStatus("Uploading...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post("/api/generate", formData);

      if (response.data.status === "processing") {
        setProcessingStatus("Processing video...");
        pollVideoStatus(response.data.output_path);
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

  const pollVideoStatus = useCallback(async (outputPath) => {
    const pollInterval = setInterval(async () => {
        try {
            const response = await axios.get(`/api/video_status?path=${encodeURIComponent(outputPath)}`);
            if (response.data.status === "completed") {
                clearInterval(pollInterval);
                setLoading(false);
                setProcessingStatus("Video processing completed");
                setDownloadUrl(`/api/download?path=videos/${encodeURIComponent(outputPath.split('/').pop())}`);
            } else if (response.data.status === "error") {
                clearInterval(pollInterval);
                setLoading(false);
                setProcessingStatus("Error: Video processing failed");
            }
        } catch (error) {
            console.error("Error polling video status", error);
        }
    }, 5000); // Poll every 5 seconds
}, []);

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
        {loading ? "Processing..." : "Upload and Generate"}
      </button>
      {processingStatus && <p className="mt-4">{processingStatus}</p>}
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