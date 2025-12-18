import React, { useState, InputHTMLAttributes } from 'react';
import { motion } from 'framer-motion';
import './GlassInput.css';

interface GlassInputProps extends InputHTMLAttributes<HTMLInputElement> {
    label?: string;
    error?: string;
}

export const GlassInput: React.FC<GlassInputProps> = ({
    label,
    error,
    className = '',
    ...props
}) => {
    const [isFocused, setIsFocused] = useState(false);
    const [hasValue, setHasValue] = useState(false);

    const handleFocus = () => setIsFocused(true);
    const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
        setIsFocused(false);
        setHasValue(e.target.value.length > 0);
    };

    return (
        <div className={`glass-input-container ${className}`}>
            {label && (
                <motion.label
                    className={`glass-input-label ${isFocused || hasValue ? 'glass-input-label--active' : ''}`}
                    animate={{
                        y: isFocused || hasValue ? -20 : 0,
                        scale: isFocused || hasValue ? 0.85 : 1,
                    }}
                    transition={{ duration: 0.2 }}
                >
                    {label}
                </motion.label>
            )}
            <input
                className={`glass-input ${error ? 'glass-input--error' : ''}`}
                onFocus={handleFocus}
                onBlur={handleBlur}
                {...props}
            />
            <div className={`glass-input-border ${isFocused ? 'glass-input-border--focused' : ''}`} />
            {error && <span className="glass-input-error">{error}</span>}
        </div>
    );
};
