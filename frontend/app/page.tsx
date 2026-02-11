"use client";

import { useState, useRef, useEffect } from "react";

export default function Home() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pdfUrl, setPdfUrl] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [error, setError] = useState("");

  const [pdfInfo, setPdfInfo] = useState({
    filename: "",
    pages: 0,
    words: 0,
    tables: 0,
    images: 0,
    flowcharts: 0,
    file_hash: "",
  });

  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<{ type: string; text: string }[]>([]);
  const [loadingAnswer, setLoadingAnswer] = useState(false);

  const [pdfPreviewUrl, setPdfPreviewUrl] = useState("");

  const chatEndRef = useRef<HTMLDivElement>(null);

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
      setPdfUrl("");
      setUploadStatus("");
      setError("");
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type === "application/pdf") {
        setSelectedFile(file);
        setPdfUrl("");
        setUploadStatus("");
        setError("");
      } else {
        setError("Only PDF files are allowed.");
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  // ---------------- Upload PDF from File ----------------
  const uploadPdfFile = async () => {
    if (!selectedFile) {
      setError("Please select a PDF file first.");
      return;
    }

    setError("");
    setUploadStatus("Uploading PDF...");
    setChat([]);
    setPdfPreviewUrl("");

    setPdfInfo({
      filename: "",
      pages: 0,
      words: 0,
      tables: 0,
      images: 0,
      flowcharts: 0,
      file_hash: "",
    });

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const res = await fetch(`${backendUrl}/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      console.log("UPLOAD RESPONSE:", data);

      if (!res.ok || data.success === false) {
        setUploadStatus("");
        setError(data.detail || data.message || "Upload failed. Check backend.");
        return;
      }

      setPdfInfo({
        filename: data.filename || selectedFile.name,
        pages: data.pages || 0,
        words: data.words || 0,
        tables: data.tables || 0,
        images: data.images || 0,
        flowcharts: data.flowcharts || 0,
        file_hash: data.file_hash || "",
      });

      setPdfPreviewUrl(`${backendUrl}/pdf/${data.file_hash}`);

      setUploadStatus("✅ PDF Uploaded Successfully!");

      setChat([
        {
          type: "bot",
          text: "PDF uploaded successfully. You can now ask questions about the document.",
        },
      ]);
    } catch (err) {
      console.log(err);
      setUploadStatus("");
      setError("Upload failed. Check backend.");
    }
  };

  // ---------------- Upload PDF from URL ----------------
  const uploadPdfUrl = async () => {
    if (!pdfUrl.trim()) {
      setError("Please paste a PDF URL first.");
      return;
    }

    setError("");
    setUploadStatus("Downloading & Uploading PDF from URL...");
    setChat([]);
    setPdfPreviewUrl("");

    try {
      const res = await fetch(`${backendUrl}/upload_url`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: pdfUrl }),
      });

      const data = await res.json();
      console.log("UPLOAD URL RESPONSE:", data);

      if (!res.ok || data.success === false) {
        setUploadStatus("");
        setError(data.detail || data.message || "Upload from URL failed.");
        return;
      }

      setPdfInfo({
        filename: data.filename || "PDF from URL",
        pages: data.pages || 0,
        words: data.words || 0,
        tables: data.tables || 0,
        images: data.images || 0,
        flowcharts: data.flowcharts || 0,
        file_hash: data.file_hash || "",
      });

      setPdfPreviewUrl(`${backendUrl}/pdf/${data.file_hash}`);

      setUploadStatus("✅ PDF Uploaded Successfully from URL!");

      setChat([
        {
          type: "bot",
          text: "PDF uploaded successfully from URL. You can now ask questions.",
        },
      ]);
    } catch (err) {
      console.log(err);
      setUploadStatus("");
      setError("Upload from URL failed. Check backend.");
    }
  };

  // ---------------- Ask Question ----------------
  const handleAsk = async () => {
    if (!question.trim()) return;

    if (!pdfInfo.file_hash) {
      setError("Upload a PDF first before asking questions.");
      return;
    }

    const userQ = question;
    setQuestion("");
    setError("");

    setChat((prev) => [...prev, { type: "user", text: userQ }]);
    setLoadingAnswer(true);

    try {
      const res = await fetch(`${backendUrl}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          file_hash: pdfInfo.file_hash,
          question: userQ,
        }),
      });

      const data = await res.json();
      console.log("ASK RESPONSE:", data);

      if (!res.ok) {
        setChat((prev) => [
          ...prev,
          { type: "bot", text: "❌ Error: Unable to fetch answer from backend." },
        ]);
        setLoadingAnswer(false);
        return;
      }

      setChat((prev) => [
        ...prev,
        { type: "bot", text: data.answer || "No answer returned." },
      ]);
    } catch (err) {
      console.log(err);
      setChat((prev) => [
        ...prev,
        { type: "bot", text: "❌ Error: Backend not responding." },
      ]);
    }

    setLoadingAnswer(false);
  };

  const handleEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleAsk();
    }
  };

  return (
    <div className="min-h-screen bg-[#0b1220] text-white flex">
      {/* LEFT PANEL */}
      <div className="w-[420px] border-r border-gray-700 p-6 flex flex-col">
        <h1 className="text-4xl font-bold mb-1">Chat With PDF</h1>
        <p className="text-gray-300 text-lg mb-6">
          Document Question Answering
        </p>

        {/* Upload Box */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          className="border-2 border-dashed border-gray-500 rounded-lg p-6 text-center bg-[#0f1b33] hover:border-gray-300 transition"
        >
          <label className="cursor-pointer block">
            <div className="text-2xl mb-2">⬆️</div>

            <p className="text-xl font-semibold mb-2">Drop your PDF here</p>
            <p className="text-gray-400 mb-4">or click to browse</p>

            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileChange}
              className="hidden"
            />
          </label>

          {selectedFile && (
            <p className="mt-3 text-sm text-gray-300 break-all">
              Selected: {selectedFile.name}
            </p>
          )}

          <button
            onClick={uploadPdfFile}
            className="mt-4 w-full bg-gray-200 text-black font-semibold py-2 rounded hover:bg-gray-300 transition"
          >
            Upload PDF
          </button>
        </div>

        {/* URL Upload */}
        <div className="mt-5 bg-[#0f1b33] border border-gray-700 rounded-lg p-4">
          <p className="text-lg font-semibold mb-2">Upload via PDF Link</p>

          <input
            type="text"
            value={pdfUrl}
            onChange={(e) => {
              setPdfUrl(e.target.value);
              setSelectedFile(null);
            }}
            placeholder="Paste PDF link here..."
            className="w-full bg-[#0b1220] border border-gray-600 rounded px-4 py-2 text-white placeholder-gray-400 outline-none"
          />

          <button
            onClick={uploadPdfUrl}
            className="mt-3 w-full bg-[#2563eb] text-white font-semibold py-2 rounded hover:bg-[#1d4ed8] transition"
          >
            Upload From Link
          </button>
        </div>

        {/* Upload Status */}
        {uploadStatus && (
          <p className="mt-4 text-green-400 font-semibold">{uploadStatus}</p>
        )}

        {/* Error */}
        {error && <p className="mt-3 text-red-500 font-semibold">❌ {error}</p>}

        {/* Document Info */}
        <div className="mt-10">
          <h2 className="text-3xl font-bold mb-4">Document Info</h2>

          {pdfInfo.filename ? (
            <div className="bg-[#0f1b33] rounded-lg p-4 border border-gray-700">
              <p className="text-lg font-semibold mb-4 break-all">
                📄 {pdfInfo.filename}
              </p>

              <div className="space-y-2 text-gray-300 text-lg">
                <p>📌 Total Pages: {pdfInfo.pages}</p>
                <p>📝 Total Words: {pdfInfo.words}</p>
                <p>📊 Total Tables: {pdfInfo.tables}</p>
                <p>🖼 Total Images: {pdfInfo.images}</p>
                <p>📈 Flowcharts / Graphs: {pdfInfo.flowcharts}</p>
              </div>

              <p className="text-sm text-gray-500 mt-4 break-all">
                Hash: {pdfInfo.file_hash}
              </p>
            </div>
          ) : (
            <p className="text-gray-400 text-lg">No PDF uploaded yet.</p>
          )}
        </div>

        <div className="flex-1"></div>
      </div>

      {/* RIGHT PANEL */}
      <div className="flex-1 flex flex-col relative">
        {/* PDF Preview */}
        <div className="h-[55%] border-b border-gray-700 bg-[#0f1b33]">
          {pdfPreviewUrl ? (
            <iframe
              src={pdfPreviewUrl}
              className="w-full h-full"
              title="PDF Preview"
            />
          ) : (
            <div className="h-full flex flex-col justify-center items-center text-gray-400">
              <div className="text-5xl mb-4">📄</div>
              <h2 className="text-3xl font-bold text-white mb-2">
                PDF Preview
              </h2>
              <p className="text-gray-400 text-lg">
                Upload a PDF to view it here.
              </p>
            </div>
          )}
        </div>

        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {chat.length === 0 ? (
            <div className="text-center mt-10">
              <div className="text-5xl mb-4">💬</div>
              <h2 className="text-3xl font-bold mb-4">
                Ask Questions About Your PDF
              </h2>
              <p className="text-gray-400 text-lg max-w-xl mx-auto">
                Upload a PDF and start chatting with it.
              </p>
            </div>
          ) : (
            chat.map((msg, index) => (
              <div
                key={index}
                className={`max-w-3xl px-5 py-4 rounded-lg text-lg whitespace-pre-line ${
                  msg.type === "user"
                    ? "ml-auto bg-[#2563eb] text-white"
                    : "mr-auto bg-[#0f1b33] border border-gray-700 text-gray-200"
                }`}
              >
                {msg.text}
              </div>
            ))
          )}

          {loadingAnswer && (
            <div className="mr-auto bg-[#0f1b33] border border-gray-700 text-white px-5 py-4 rounded-lg max-w-3xl">
              <span className="animate-pulse">Typing...</span>
            </div>
          )}

          <div ref={chatEndRef}></div>
        </div>

        {/* Chat Input */}
        <div className="border-t border-gray-700 bg-[#0b1220] p-5 flex items-center gap-4">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleEnter}
            placeholder="Ask about your PDF..."
            className="flex-1 bg-[#0f1b33] border border-gray-700 rounded-xl px-6 py-4 text-white placeholder-gray-400 outline-none text-lg"
            style={{ color: "white" }}
          />

          <button
            onClick={handleAsk}
            className="bg-white text-black px-6 py-4 rounded-xl font-bold hover:bg-gray-300 transition text-lg"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}
