'use client'
import { useState, useCallback, useEffect, useRef } from "react";
import { ChangeEvent, DragEvent } from "react";
import axios from "axios";
import Image from 'next/image';
import Cookies from 'js-cookie';
import crypto from 'crypto';
import { v4 as uuidv4 } from 'uuid';
import Footer from "@/components/footer";

const generateHash = (input: string) => {
  return crypto.createHash('sha256').update(input).digest('hex').slice(0, 10);
};

const VIDDYSCRIBE_API_KEY = process.env.VIDDYSCRIBE_API_KEY;

const backendUrl = process.env.NODE_ENV === 'development'
  ? 'http://localhost:8080'
  : 'https://dezcribe-gcp-cloud-781700989023.us-central1.run.app';
const getClientId = () => {
  let clientId = Cookies.get('clientId');
  if (!clientId) {
    clientId = Date.now().toString();
    Cookies.set('clientId', clientId, { expires: 7 });
  }
  return clientId;
};

const clientId = getClientId();

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [selectedSampleVideo, setSelectedSampleVideo] = useState<string | null>(null);
  const [sampleVideosLoading, setSampleVideosLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [lastUploadedFileName, setLastUploadedFileName] = useState<string | null>(null);
  const lastUploadedFileNameRef = useRef<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [processingStatus, setProcessingStatus] = useState("");
  const MAX_FILE_SIZE = 100 * 1024 * 1024;
  const [addBgMusic, setAddBgMusic] = useState(false);
  const [sampleVideos, setSampleVideos] = useState<{ name: string, url?: string, file?: File }[]>([]);
  
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      const selectedFile = event.target.files[0];
      const validExtensions = ['mov', 'mpeg', 'mp4', 'mpg', 'avi', 'wmv', 'mpegps', 'flv'];
      const fileExtension = selectedFile.name.split('.').pop()?.toLowerCase();

      if (!fileExtension || !validExtensions.includes(fileExtension)) {
        alert("Invalid file type. Please upload a video file (mov, mpeg, mp4, mpg, avi, wmv, mpegps, flv).");
        return;
      }

      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 100MB limit. Please choose a smaller file.");
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
        setSelectedSampleVideo(null);
      };
      video.src = URL.createObjectURL(selectedFile);
    }
  };

  const handleDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      const selectedFile = event.dataTransfer.files[0];
      const validExtensions = ['mov', 'mpeg', 'mp4', 'mpg', 'avi', 'wmv', 'mpegps', 'flv'];
      const fileExtension = selectedFile.name.split('.').pop()?.toLowerCase();

      if (!fileExtension || !validExtensions.includes(fileExtension)) {
        alert("Invalid file type. Please upload a video file (mov, mpeg, mp4, mpg, avi, wmv, mpegps, flv).");
        return;
      }

      if (selectedFile.size > MAX_FILE_SIZE) {
        alert("File size exceeds the 100MB limit. Please choose a smaller file.");
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
        setSelectedSampleVideo(null);
        event.dataTransfer.clearData();
      };
      video.src = URL.createObjectURL(selectedFile);
    }
  }, []);

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };
  
const handleUpload = async () => {
  if (!file && !selectedSampleVideo) return;
  setLoading(true);
  setProcessingStatus("Uploading...");
  setDownloadUrl("");

  let uploadFile: File | null = file;
  let hashedFileName: string;

  if (selectedSampleVideo) {
    const selectedVideo = sampleVideos.find(video => video.name === selectedSampleVideo);
    if (!selectedVideo) {
      setLoading(false);
      setProcessingStatus("Error: Sample video not found");
      return;
    }
    uploadFile = selectedVideo.file || null;
  }

  if (uploadFile) {
    const uuid = uuidv4();
    const hash = generateHash(uploadFile.name + Date.now().toString());
    hashedFileName = `${uploadFile.name.replace(/\.[^/.]+$/, "")}_${hash}_${uuid}${uploadFile.name.match(/\.[^/.]+$/)?.[0]}`;
    setLastUploadedFileName(hashedFileName);
    lastUploadedFileNameRef.current = hashedFileName;

    try {
      // Get signed URL for upload
      const { data: { upload_url } } = await axios.post(`${backendUrl}/get_upload_url`, {
        filename: hashedFileName,
        contentType: uploadFile.type  // Make sure this is included
      }, {
        headers: {
          'Authorization': `Bearer ${VIDDYSCRIBE_API_KEY}`,
          'Content-Type': 'application/json'  // Specify the content type of the request
        }
      });

      // Upload file directly to GCS
      await axios.put(upload_url, uploadFile, {
        headers: {
          'Content-Type': uploadFile.type
        }
      });

      // Notify backend to start processing
      const response = await axios.post(`${backendUrl}/start_processing`, {
        filename: hashedFileName,
        add_bg_music: addBgMusic
      }, {
        headers: {
          'Authorization': `Bearer ${VIDDYSCRIBE_API_KEY}`
        }
      });

      const { output_video_name } = response.data;
      console.log("Upload successful, starting to poll for status");
      pollForStatus(output_video_name);

    } catch (error) {
      console.error("Error uploading file:", error);
      setProcessingStatus("Error: Failed to upload file");
      setLoading(false);
    }
  }
};


const pollForStatus = async (outputVideoName: string) => {
  const pollInterval = 10000;
  const maxAttempts = 300;
  let attempts = 0;

  const checkStatus = async () => {
    try {
      console.log(`Checking status for: ${outputVideoName}, attempt: ${attempts}`);
      const response = await axios.get(`${backendUrl}/update_status/${outputVideoName}`);
      const { status } = response.data;
      console.log(`Status response: ${status}`);
      setProcessingStatus(status);

      if (status !== "Processing completed" && attempts < maxAttempts) {
        attempts++;
        setTimeout(checkStatus, pollInterval);
      } else if (status === "Processing completed") {
        pollForSignedUrl(outputVideoName);
      }
    } catch (error) {
      console.error("Error checking status:", error);
      if (attempts < maxAttempts) {
        attempts++;
        setTimeout(checkStatus, pollInterval);
      } else {
        setProcessingStatus("Error: Failed to retrieve status");
      }
    }
  };

  checkStatus();
};

  const pollForSignedUrl = async (outputVideoName: string) => {
    const pollInterval = 3000;
    const maxAttempts = 3;
    let attempts = 0;

    const checkStatus = async () => {
      try {
        const response = await axios.get(`${backendUrl}/download_video/${outputVideoName}`);
        const { signed_url } = response.data;
        if (signed_url) {
          setDownloadUrl(signed_url);
          setLoading(false);
          setProcessingStatus("Video processing completed");
        } else if (attempts < maxAttempts) {
          attempts++;
          setTimeout(checkStatus, pollInterval);
        } else {
          setProcessingStatus("Error: Failed to retrieve signed URL");
        }
      } catch (error) {
        console.error("Error checking video status:", error);
        if (attempts < maxAttempts) {
          attempts++;
          setTimeout(checkStatus, pollInterval);
        } else {
          setProcessingStatus("Error: Failed to retrieve signed URL");
        }
      }
    };

    checkStatus();
  };

  const triggerDownload = (url: string, filename: string) => {
    fetch(url)
      .then(response => response.blob())
      .then(blob => {
        const blobUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(blobUrl);
      })
      .catch(error => {
        console.error('Download failed:', error);
        alert('Download failed. Please try again.');
      });
  };

  const fetchSampleVideos = async () => {
    try {
      const response = await axios.get(`${backendUrl}/download_sample_videos`);
      const videos = await Promise.all(response.data.map(async (video: { name: string, url: string }) => {
        const videoResponse = await axios.get(video.url, { responseType: 'blob' });
        const videoFile = new File([videoResponse.data], video.name, { type: 'video/mp4' });
        return { name: video.name, url: video.url, file: videoFile };
      }));
      return videos;
    } catch (error) {
      console.error("Error fetching sample videos:", error);
      return [];
    } finally {
      setSampleVideosLoading(false);
    }
  };

  useEffect(() => {
    const loadSampleVideos = async () => {
      const videos = await fetchSampleVideos();
      setSampleVideos(videos);
    };
    loadSampleVideos();
  }, []);

  // Add this useEffect to reset the file state when a sample video is selected
  useEffect(() => {
    if (selectedSampleVideo) {
      setFile(null);
    }
  }, [selectedSampleVideo]);

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

  return (
    <main className="flex flex-col min-h-screen">
      <div className="flex-grow flex flex-col items-center justify-start gap-12 px-4 lg:px-24 pt-6 lg:pt-12 pb-12 lg:pb-24 bg-black bg-zinc-950/20">
      <div className="flex flex-row items-center">
        <div className="items-center justify-center">
          <div className="flex flex-row items-center justify-center gap-2">
            <Image src="/viddy_logo.png" alt="Viddyscribe Logo" width={90} height={90} className=" h-12 w-12" />
            <p className="text-3xl text-zinc-100 text-center font-bold">ViddyScribe</p>
            <sub className="text-sm mt-1 text-zinc-100/70 subscript font-bold">Beta</sub>
          </div>
          <p className="text-sm lg:text-md text-zinc-100/50 mt-3">Add audio description to videos with AI</p>
        </div>
      </div>

      <div className="max-w-lg xl:max-w-xl w-full">
        <div className="flex flex-col items-center my-3">
          {sampleVideosLoading ? (
            <p className="text-zinc-400 text-center">Loading sample videos...</p>
          ) : (
            <div>
            <p className="text-zinc-100 text-lg text-center mb-8">Try with a sample video or upload your own</p>
            <div className="grid grid-cols-2   gap-4">
              {sampleVideos.map((video) => (
                <div
                  key={video.name}
                  className={`p-4 rounded-lg text-center mb-4 cursor-pointer ${selectedSampleVideo === video.name ? 'bg-zinc-700' : 'bg-zinc-900 hover:bg-zinc-800'} ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                  onClick={() => !loading && setSelectedSampleVideo(video.name)}
                >
                  <video className="w-full rounded-lg" controls>
                    <source src={video.url} type="video/mp4" />
                    Your browser does not support the video tag.
                  </video>
                  <p className="text-zinc-100/80 mt-2">
                    <input
                      type="checkbox"
                      checked={selectedSampleVideo === video.name}
                      readOnly
                      className={`mr-2 ${selectedSampleVideo === video.name ? 'text-violet-500' : ''}`}
                    />
                    {video.name}
                  </p>
                </div>
              ))}
            </div>
          </div>
          )}
        </div>
        <div
          className={`p-8 border-2 transition-all  border-white/50 border-dashed rounded-xl text-center cursor-pointer text-zinc-100/70 ${file || selectedSampleVideo ? 'bg-zinc-700 hover:bg-zinc-800 border-none' : 'bg-zinc-900 hover:bg-zinc-800'} ${loading ? 'opacity-70' : ''}`}
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
          <p className=" lg:text-lg overflow-x-hidden">
            {file ? <><b>Selected video</b> {file.name}</> : selectedSampleVideo ? <><b>Selected sample video</b> {selectedSampleVideo}</> : "Drag & Drop or Tap here to choose file"}
          </p>
          <p className=" text-zinc-100 text-center text-xs lg:text-sm  mt-3">Currently supports video files &lt; 100 MB and duration &lt; 2 minutes.</p>
        </div>
        <div className="items-center justify-center flex mt-4">
          <label className="text-zinc-100 text-sm checkbox-container">
            <input
              type="checkbox"
              checked={addBgMusic}
              onChange={(e) => setAddBgMusic(e.target.checked)}
              className="mr-2 checkbox "
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
          disabled={loading || (!file && !selectedSampleVideo)}
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
       

       {downloadUrl && (
  <button
    onClick={() => {
      const originalFileName = lastUploadedFileNameRef.current || 'video.mp4';
      
      // List of common video file extensions
      const videoExtensions = ['mp4', 'mov', 'avi', 'wmv', 'flv', 'webm', 'mkv', 'm4v'];
      
      // Extract the base name and extension
      const match = originalFileName.match(/^(.+?)_[^_]+_[^_]+(?:\.([^.]+))?$/i);
      
      let baseFileName = 'video';
      let fileExtension = 'mp4';
      
      if (match) {
        baseFileName = match[1];
        if (match[2] && videoExtensions.includes(match[2].toLowerCase())) {
          fileExtension = match[2].toLowerCase();
        }
      }
      
      // Construct the new file name
      const newFileName = `${baseFileName}_with_audio_desc.${fileExtension}`;
      
      console.log('Original filename:', originalFileName);
      console.log('Base filename:', baseFileName);
      console.log('File extension:', fileExtension);
      console.log('New filename:', newFileName);
      
      triggerDownload(downloadUrl, newFileName);
    }}
    className="mt-4 btn btn-download"
  >
    Download Video
  </button>
)}

      </div>
      </div>
      <Footer />
    </main>
    
  );
}