"use client"
import { useEffect, useRef } from "react"
import confetti from "canvas-confetti"

export function Confetti({ fire }: { fire: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (!fire || !canvasRef.current) return
    const myConfetti = confetti.create(canvasRef.current, { resize: true, useWorker: true })
    // Center burst
    myConfetti({ particleCount: 200, spread: 90, origin: { x: 0.5, y: 0.4 } })
    // Side bursts
    setTimeout(() => myConfetti({ particleCount: 80, angle: 60, spread: 70, origin: { x: 0, y: 0.6 } }), 200)
    setTimeout(() => myConfetti({ particleCount: 80, angle: 120, spread: 70, origin: { x: 1, y: 0.6 } }), 400)
    // Gentle rain for 5 seconds
    const end = Date.now() + 5000
    const frame = () => {
      myConfetti({
        particleCount: 3, angle: 90, spread: 55,
        origin: { x: Math.random(), y: 0 },
        gravity: 0.8, scalar: 0.9,
      })
      if (Date.now() < end) requestAnimationFrame(frame)
    }
    frame()
  }, [fire])
  return (
    <canvas
      ref={canvasRef}
      style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9999 }}
    />
  )
}
