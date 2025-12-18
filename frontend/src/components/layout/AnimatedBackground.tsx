import React from 'react';
import { motion } from 'framer-motion';

export const AnimatedBackground: React.FC = () => {
    return (
        <div className="fixed inset-0 -z-10 overflow-hidden bg-black">
            <motion.div
                className="absolute -inset-[50%] opacity-30"
                animate={{
                    rotate: [0, 360],
                }}
                transition={{
                    duration: 20,
                    repeat: Infinity,
                    ease: "linear"
                }}
                style={{
                    background: 'conic-gradient(from 0deg at 50% 50%, #FF0080, #7928CA, #FF0080)',
                    filter: 'blur(100px)',
                }}
            />
            <div className="absolute inset-0 bg-black/50 backdrop-blur-3xl" />
        </div>
    );
};
