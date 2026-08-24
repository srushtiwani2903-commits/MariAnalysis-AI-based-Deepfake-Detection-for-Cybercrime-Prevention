import { useEffect, useRef } from "react";
import { useTheme } from "../context/ThemeContext";

// Canvas particle network background - animated cybersecurity backdrop
export default function ParticleBackground({ density = 70, className = "" }) {
  const canvasRef = useRef(null);
  const { dark } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    let raf;
    let particles = [];
    let mouse = { x: -999, y: -999 };

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    class Particle {
      constructor() {
        this.reset();
      }
      reset() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.vx = (Math.random() - 0.5) * 0.5;
        this.vy = (Math.random() - 0.5) * 0.5;
        this.r = Math.random() * 1.8 + 0.4;
      }
      move() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        // gentle mouse repel
        const dx = this.x - mouse.x;
        const dy = this.y - mouse.y;
        const dist = Math.hypot(dx, dy);
        if (dist < 100) {
          this.x += (dx / dist) * 0.6;
          this.y += (dy / dist) * 0.6;
        }
      }
    }

    for (let i = 0; i < density; i++) particles.push(new Particle());

    // Theme-aware particle palette: neon blue/purple in dark, cyber green in light
    const colors = dark
      ? ["34, 211, 238", "124, 58, 237", "0, 229, 255"]
      : ["21, 128, 61", "5, 150, 105", "22, 163, 74"];

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // connections
      ctx.lineWidth = 0.6;
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i];
          const b = particles[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 130) {
            const alpha = (1 - d / 130) * 0.4;
            ctx.strokeStyle = `rgba(${colors[i % colors.length]}, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
      // particles
      particles.forEach((p, i) => {
        p.move();
        ctx.fillStyle = `rgba(${colors[i % colors.length]}, 0.8)`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      });
      raf = requestAnimationFrame(draw);
    };
    draw();

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
    };
    const onLeave = () => { mouse.x = -999; mouse.y = -999; };
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseleave", onLeave);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("mouseleave", onLeave);
    };
  }, [density, dark]);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full pointer-events-none ${className}`}
      aria-hidden="true"
    />
  );
}
