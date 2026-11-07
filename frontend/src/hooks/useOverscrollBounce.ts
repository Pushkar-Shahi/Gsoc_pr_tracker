import { useEffect, useRef, useState } from 'react';

export function useOverscrollBounce() {
  const [bounceStyle, setBounceStyle] = useState<{
    transform: string;
    transition: string;
    willChange?: string;
  }>({
    transform: 'translate3d(0, 0, 0)',
    transition: 'none',
  });

  const startYRef = useRef<number | null>(null);
  const isPullingRef = useRef<boolean>(false);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    // Only apply on touch devices (phones and tablets)
    if (typeof window === 'undefined' || !('ontouchstart' in window)) {
      return;
    }

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length !== 1) return;
      startYRef.current = e.touches[0].clientY;
      isPullingRef.current = false;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (startYRef.current === null || e.touches.length !== 1) return;
      const currentY = e.touches[0].clientY;
      const rawDelta = currentY - startYRef.current;
      const scrollY = window.scrollY || document.documentElement.scrollTop;
      const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);

      // Check if user is at the top pulling down
      if (scrollY <= 0 && rawDelta > 0) {
        isPullingRef.current = true;
      }
      // Check if user is at the bottom pulling up
      else if (scrollY >= maxScroll - 2 && rawDelta < 0) {
        isPullingRef.current = true;
      } else {
        if (isPullingRef.current) {
          isPullingRef.current = false;
          setBounceStyle({
            transform: 'translate3d(0, 0, 0)',
            transition: 'transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
            willChange: 'transform',
          });
        }
        return;
      }

      if (isPullingRef.current) {
        // Logarithmic rubber-band spring dampening (physical Android 12 / iOS stretch curve)
        const damped = Math.sign(rawDelta) * Math.min(85, Math.pow(Math.abs(rawDelta), 0.72) * 2.2);

        if (animFrameRef.current) {
          cancelAnimationFrame(animFrameRef.current);
        }
        animFrameRef.current = requestAnimationFrame(() => {
          setBounceStyle({
            transform: `translate3d(0, ${damped}px, 0)`,
            transition: 'none',
            willChange: 'transform',
          });
        });
      }
    };

    const onTouchEnd = () => {
      startYRef.current = null;
      if (isPullingRef.current) {
        isPullingRef.current = false;
        if (animFrameRef.current) {
          cancelAnimationFrame(animFrameRef.current);
        }
        // Spring bounce back to initial state with elastic overshoot
        setBounceStyle({
          transform: 'translate3d(0, 0, 0)',
          transition: 'transform 0.48s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
          willChange: 'transform',
        });
      }
    };

    window.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('touchend', onTouchEnd, { passive: true });
    window.addEventListener('touchcancel', onTouchEnd, { passive: true });

    return () => {
      window.removeEventListener('touchstart', onTouchStart);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
      window.removeEventListener('touchcancel', onTouchEnd);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, []);

  return bounceStyle;
}

