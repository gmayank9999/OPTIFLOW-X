import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Shell } from "@/components/Shell";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "OPTIFLOW-X",
  description: "Measurement-driven multi-agent optimization of C/C++ programs",
};

// Applies the saved theme before first paint, so there's no light flash.
const themeScript = `try{var t=localStorage.getItem("optiflow-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-sans text-[13.5px] leading-[1.5]">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
