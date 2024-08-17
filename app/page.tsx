'use client'
import { useState, useCallback, useEffect, useRef } from "react";
import { ChangeEvent, DragEvent } from "react";
import axios from "axios";
import Image from 'next/image';
import Cookies from 'js-cookie';
import crypto from 'crypto';



const generateHash = (input: string) => {
  return crypto.createHash('sha256').update(input).digest('hex').slice(0, 10);
};

const getClientId = () => {
  let clientId = Cookies.get('clientId');
  if (!clientId) {
    clientId = Date.now().toString();
    Cookies.set('clientId', clientId, { expires: 7 }); // Set cookie to expire in 7 days
  }
  return clientId;
};

const clientId = getClientId(); // Retrieve or generate client ID

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUploadedFileName, setLastUploadedFileName] = useState<string | null>(null);
  const lastUploadedFileNameRef = useRef<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");
  const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB
  const [addBgMusic, setAddBgMusic] = useState(false);
  const socketRef = useRef<WebSocket | null>(null); // Use ref to store WebSocket instance
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null); // Use ref to store polling interval
  const wsTimeoutRef = useRef<NodeJS.Timeout | null>(null); // Use ref to store WebSocket timeout

  useEffect(() => {
    const isProd = process.env.NODE_ENV === 'production';
    const wsUrl = isProd ? 'wss://testing.viddyscribe.com/ws' : 'ws://localhost:8001/ws';
    const reconnectInterval = 5000; // 5 seconds
    const pollingInterval = 5000; // 5 seconds
    const wsTimeout = 30000; // 10 seconds

    const checkVideoStatus = async () => {
      if (!lastUploadedFileNameRef.current) {
        console.warn("No file name set for checking video status.");
        return;
      }
      try {
        const response = await axios.get(`/api/check_status`, {
          params: { client_id: clientId, file_name: lastUploadedFileNameRef.current }
        });
        const { status, output_path, message } = response.data;
        if (status === "completed") {
          setLoading(false);
          setProcessingStatus("Video processing completed");
          const encodedPath = encodeURIComponent(output_path);
          setDownloadUrl(`api/download/?path=${encodedPath}`);
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
          }
        } else if (status === "error") {
          setLoading(false);
          setProcessingStatus(`Error: ${message}`);
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
          }
        }
      } catch (error) {
        console.error("Error checking video status:", error);
      }
    };

    const startPolling = () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      pollingIntervalRef.current = setInterval(checkVideoStatus, pollingInterval);
    };

    const connectWebSocket = () => {
      console.log(`Connecting to WebSocket server at: ${wsUrl}?client_id=${clientId}`);
      const socket = new WebSocket(`${wsUrl}?client_id=${clientId}`);
      socketRef.current = socket; // Store WebSocket instance in ref

      socket.onopen = () => {
        console.log("Connected to WebSocket server");
        if (wsTimeoutRef.current) {
          clearTimeout(wsTimeoutRef.current);
        }
        wsTimeoutRef.current = setTimeout(startPolling, wsTimeout); // Start polling if no message received within timeout
      };

      socket.onmessage = (event) => {
        console.log("Received message from WebSocket:", event.data);
        if (event.data === "ping") {
          console.log("Received 'ping' message from WebSocket");
          return; // Ignore ping messages
        }
        const message = JSON.parse(event.data);
        if (message.status === "completed") {
          console.log("Received 'completed' event from WebSocket");
          setLoading(false);
          setProcessingStatus("Video processing completed");
          const encodedPath = encodeURIComponent(message.output_path);
          setDownloadUrl(`api/download/?path=${encodedPath}`);
          if (wsTimeoutRef.current) {
            clearTimeout(wsTimeoutRef.current);
          }
        } else if (message.status === "error") {
          console.log("Received 'error' event from WebSocket");
          setLoading(false);
          setProcessingStatus(`Error: ${message.message}`);
          if (wsTimeoutRef.current) {
            clearTimeout(wsTimeoutRef.current);
          }
        }
      };

      socket.onclose = (event) => {
        console.log(`Disconnected from WebSocket server. Code: ${event.code}, Reason: ${event.reason}`);
        if (event.code !== 1000) { // 1000 means normal closure
          setTimeout(connectWebSocket, reconnectInterval); // Attempt to reconnect after a delay
        } else {
          startPolling(); // Fallback to polling if WebSocket connection fails
        }
      };

      socket.onerror = (error) => {
        console.error("WebSocket error:", error);
        socket.close(); // Close the socket on error to trigger reconnection
      };
    };

    connectWebSocket(); // Initial connection

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (wsTimeoutRef.current) {
        clearTimeout(wsTimeoutRef.current);
      }
    };
  }, [lastUploadedFileName]);


  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      const selectedFile = event.target.files[0];
      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 100MB limit. Please choose a smaller file.");
        return;
      }

      const video = document.createElement('video');
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        window.URL.revokeObjectURL(video.src);
        if (video.duration > 300) {
          alert("Video duration exceeds the 5 minutes limit. Please choose a shorter video.");
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
        alert("File size exceeds the 100MB limit. Please choose a smaller file.");
        return;
      }

      const video = document.createElement('video');
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        window.URL.revokeObjectURL(video.src);
        if (video.duration > 300) {
          alert("Video duration exceeds the 5 minutes limit. Please choose a shorter video.");
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
    const hash = generateHash(file.name + Date.now().toString());
    const hashedFileName = `${file.name.replace(/\.[^/.]+$/, "")}_${hash}${file.name.match(/\.[^/.]+$/)?.[0]}`;
    setLastUploadedFileName(hashedFileName);
    lastUploadedFileNameRef.current = hashedFileName;
    const VIDDYSCRIBE_API_KEY = process.env.VIDDYSCRIBE_API_KEY;

    // Create a new File object with the hashed filename
    const hashedFile = new File([file], hashedFileName, { type: file.type });


    const formData = new FormData();
    formData.append("file", hashedFile);
    formData.append("add_bg_music", addBgMusic.toString());
    formData.append("client_id", clientId);  // Use clientId directly

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

  const handleSampleVideoSelect = (videoPath: string, videoName: string) => {
    fetch(videoPath)
      .then(response => response.blob())
      .then(blob => {
        const file = new File([blob], videoName, { type: 'video/mp4' });
        setFile(file);
      })
      .catch(error => console.error("Error loading sample video:", error));
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-start gap-12  px-4 lg:px-24 pt-6 lg:pt-12 pb-12 lg:pb-24">
     <div className="flex flex-row items-center">
      
      <div className="items-center justify-center">
        <div className="flex flex-row items-center justify-center gap-2">
        <Image src="/viddy_logo.png" alt="ViddyScribe Logo" width={90} height={90} className=" h-12 w-12" />
        <p className="text-4xl text-zinc-100 text-center font-bold">ViddyScribe</p>
        </div>
        <p className="text-sm lg:text-lg text-zinc-100/50 mt-1">Add Audio description to videos with AI</p>
      </div>
    </div>

      

      <div className="max-w-xl w-full">
      <div className="flex flex-col items-center my-10">
          <p className="text-zinc-400 text-center mb-4">Choose a sample video or try your own</p>
          <div className="grid grid-cols-2 gap-4">
            <div
              className={`p-4 rounded-lg text-center cursor-pointer ${file?.name === 'shoes_ad.mp4' ? 'bg-zinc-700' : 'bg-zinc-800'} ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
              onClick={() => !loading && handleSampleVideoSelect('/static/test_videos/shoes_ad.mp4', 'shoes_ad.mp4')}
            >
              <video className="w-full rounded-lg" controls>
                <source src="/static/test_videos/shoes_ad.mp4" type="video/mp4" />
                Your browser does not support the video tag.
              </video>
              <p className="text-zinc-100 mt-2">Shoes Ad</p>
            </div>
            <div
              className={`p-4 rounded-lg text-center cursor-pointer ${file?.name === 'all_star.mp4' ? 'bg-zinc-700' : 'bg-zinc-800'} ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
              onClick={() => !loading && handleSampleVideoSelect('/static/test_videos/all_star.mp4', 'all_star.mp4')}
            >
              <video className="w-full rounded-lg" controls>
                <source src="/static/test_videos/all_star.mp4" type="video/mp4" />
                Your browser does not support the video tag.
              </video>
              <p className="text-zinc-100 mt-2">All Star</p>
            </div>
          </div>
        </div>
        <div
          className={`p-8 lg:p-12 border-2 transition-all border-white/50 border-dashed rounded-xl text-center cursor-pointer text-zinc-100/70 ${file ? 'bg-zinc-700 hover:bg-zinc-800 border-none' : 'bg-zinc-900 hover:bg-zinc-800'} ${loading ? 'opacity-70' : ''}`}
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
          <p className=" text-zinc-100 text-center text-sm lg:text-md  mt-3">Currently supports only .mp4 files &lt; 100 MB and duration &lt; 5 minutes.</p>
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
      <div className="flex flex-col align-center justify-center text-center">
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