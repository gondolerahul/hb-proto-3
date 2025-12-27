import React from 'react';
import { motion } from 'framer-motion';
import './GlassCard.css';

interface GlassCardProps {
    children: React.ReactNode;
    className?: string;
    hover?: boolean;
    onClick?: () => void;
}

export const GlassCard: React.FC<GlassCardProps> = ({
    children,
    className = '',
    hover = false,
    onClick
}) => {
    return (
        <motion.div
            className={`glass-card ${hover ? 'glass-card--hover' : ''} ${className}`}
            whileHover={hover ? { y: -4, transition: { duration: 0.2 } } : {}}
            onClick={onClick}
        >
            <div className="glass-card-content">
                {children}
            </div>
            <div className="glass-card-shine" />
        </motion.div>
    );
};
