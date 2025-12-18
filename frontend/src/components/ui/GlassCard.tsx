import React from 'react';
import './GlassCard.css';

interface GlassCardProps {
    children: React.ReactNode;
    className?: string;
    variant?: 'default' | 'light' | 'heavy';
    hover?: boolean;
}

export const GlassCard: React.FC<GlassCardProps> = ({
    children,
    className = '',
    variant = 'default',
    hover = false,
}) => {
    const variantClass = variant === 'light' ? 'glass-light' : variant === 'heavy' ? 'glass-heavy' : 'glass';
    const hoverClass = hover ? 'glass-card--hover' : '';

    return (
        <div className={`glass-card ${variantClass} ${hoverClass} ${className}`}>
            {children}
        </div>
    );
};
