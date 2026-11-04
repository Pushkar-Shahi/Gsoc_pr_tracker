import React from 'react';

interface BrandIconProps {
  size?: number;
  className?: string;
  showBadge?: boolean;
}

export const BrandIcon: React.FC<BrandIconProps> = ({ 
  size = 36, 
  className = '',
  showBadge = true 
}) => {
  return (
    <svg 
      xmlns="http://www.w3.org/2000/svg" 
      viewBox="0 0 512 512" 
      width={size} 
      height={size}
      className={`shrink-0 ${className}`}
      aria-label="Issue-to-PR Logo"
    >
      <defs>
        <linearGradient id="brandBgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0e1424"/>
          <stop offset="100%" stopColor="#070b14"/>
        </linearGradient>
        <linearGradient id="brandLineGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#10b981"/>
          <stop offset="100%" stopColor="#06b6d4"/>
        </linearGradient>
        <filter id="brandGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="14" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {showBadge && (
        <>
          <rect width="512" height="512" rx="112" fill="url(#brandBgGrad)"/>
          <rect x="8" y="8" width="496" height="496" rx="104" fill="none" stroke="#1f293d" strokeWidth="6"/>
          <circle cx="256" cy="256" r="160" fill="none" stroke="#10b981" strokeWidth="2" strokeDasharray="8 8" opacity="0.25"/>
        </>
      )}
      
      {/* Glowing Git Branch & PR Lines */}
      <g filter="url(#brandGlow)">
        {/* Main stem */}
        <path d="M180 140 L180 372" stroke="url(#brandLineGrad)" strokeWidth="32" strokeLinecap="round"/>
        {/* Branch curve */}
        <path d="M180 230 C 230 230, 332 210, 332 290 L332 372" stroke="url(#brandLineGrad)" strokeWidth="32" strokeLinecap="round" fill="none"/>
      </g>
      
      {/* Nodes */}
      <circle cx="180" cy="140" r="34" fill="#10b981" stroke="#0e1424" strokeWidth="8"/>
      <circle cx="180" cy="372" r="34" fill="#10b981" stroke="#0e1424" strokeWidth="8"/>
      <circle cx="332" cy="372" r="34" fill="#06b6d4" stroke="#0e1424" strokeWidth="8"/>

      {/* Sparkle Accent at top branch */}
      <path d="M332 144 L336 166 L358 170 L336 174 L332 196 L328 174 L306 170 L328 166 Z" fill="#38bdf8"/>
    </svg>
  );
};

