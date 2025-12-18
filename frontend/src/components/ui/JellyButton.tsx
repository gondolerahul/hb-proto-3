import React from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import './JellyButton.css';

interface JellyButtonProps extends Omit<HTMLMotionProps<'button'>, 'whileHover' | 'whileTap'> {
    children: React.ReactNode;
    variant?: 'primary' | 'secondary' | 'ghost';
    roseGold?: boolean;
}

export const JellyButton: React.FC<JellyButtonProps> = ({
    children,
    variant = 'primary',
    roseGold = false,
    className = '',
    ...props
}) => {
    const variantClass = `jelly-button--${variant}`;
    const roseClass = roseGold ? 'jelly-button--rose' : '';

    return (
        <motion.button
            className={`jelly-button ${variantClass} ${roseClass} ${className}`}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            transition={{
                type: 'spring',
                stiffness: 400,
                damping: 10,
            }}
            {...props}
        >
            {children}
        </motion.button>
    );
};
