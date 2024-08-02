'use client'
import { useState } from "react";
import { ChangeEvent } from "react";
export default function Home() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false); // Add loading state

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files[0]);
  };
  const handleUpload = async () => {
    if (!file) return;

    setLoading(true); // Set loading to true when upload starts

    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/generate", {
      method: "POST",
      body: formData,
    });

    setLoading(false); // Set loading to false when upload ends

    if (response.ok) {
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "output_video.mp4";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } else {
      console.error("Failed to generate video");
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      <div className="mt-8">
        <input type="file" onChange={handleFileChange} />
        <button onClick={handleUpload} className="ml-4 p-2 bg-blue-500 text-white rounded" disabled={loading}>
          {loading ? "Uploading..." : "Upload and Generate"}
        </button>
      </div>
    </main>
  );
}