"use client";

import Image from "next/image";
import Link from "next/link";
import { Sparkles, Cpu } from "lucide-react";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
}

export default function Logo({ size = "md", showText = true }: LogoProps) {
  const dimensions = {
    sm: { img: 30, text: "text-sm", sub: "text-[9px]" },
    md: { img: 42, text: "text-base", sub: "text-[10px]" },
    lg: { img: 54, text: "text-xl", sub: "text-[11px]" },
  }[size];

  return (
    <Link href="/" className="group flex items-center gap-3 transition">
      {/* 3D Glassmorphism Logo Badge */}
      <div className="relative flex items-center justify-center rounded-2xl bg-gradient-to-tr from-slate-900 via-emerald-950 to-cyan-950 p-1.5 shadow-xl shadow-emerald-900/30 border border-emerald-400/40 group-hover:scale-105 group-hover:border-cyan-400/60 transition-all duration-300">
        <div className="overflow-hidden rounded-xl bg-slate-950 shadow-inner">
          <Image
            src="/logo-3d.jpg"
            alt="AI Employee OS 3D Logo"
            width={dimensions.img}
            height={dimensions.img}
            className="object-cover transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3"
            priority
          />
        </div>
        <span className="absolute -top-1 -right-1 flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500 border border-white/20"></span>
        </span>
      </div>

      {showText && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className={`font-black tracking-tight text-slate-900 leading-none ${dimensions.text}`}>
              AI<span className="bg-gradient-to-r from-emerald-600 via-teal-500 to-cyan-600 bg-clip-text text-transparent">_EMPLOYEE</span>
            </span>
            <span className="rounded-md bg-emerald-950 px-1.5 py-0.5 text-[10px] font-mono font-extrabold text-emerald-400 border border-emerald-500/30">
              OS
            </span>
          </div>
          <div className="flex items-center gap-1 mt-1">
            <Cpu className="h-3 w-3 text-emerald-500 animate-pulse" />
            <span className={`font-bold uppercase tracking-widest text-slate-400 leading-none ${dimensions.sub}`}>
              Turnkey Autonomous Engine
            </span>
          </div>
        </div>
      )}
    </Link>
  );
}
