import "./globals.css";

export const metadata = {
  title: "Chat With PDF",
  description: "Chat with PDF using FastAPI + Groq + RAG",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
