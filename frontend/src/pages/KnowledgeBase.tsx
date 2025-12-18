import React, { useState, useRef, useEffect } from 'react';
import { GlassCard, JellyButton } from '@/components/ui';
import { Upload, FileText, Trash2, Loader, Search } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import './KnowledgeBase.css';

interface Document {
    id: string;
    filename: string;
    file_type: string;
    file_size?: string;
    upload_status: 'processing' | 'completed' | 'failed';
    created_at: string;
    updated_at: string;
}

interface SearchResult {
    chunk_id: string;
    document_id: string;
    filename: string;
    content: string;
    similarity: number;
}

export const KnowledgeBase: React.FC = () => {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [uploading, setUploading] = useState(false);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
    const [searching, setSearching] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        loadDocuments();
    }, []);

    const loadDocuments = async () => {
        try {
            const { data } = await apiClient.get('/ai/documents');
            setDocuments(data);
        } catch (error) {
            console.error('Failed to load documents:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        setUploading(true);

        for (const file of Array.from(files)) {
            try {
                // Create FormData for multipart/form-data upload
                const formData = new FormData();
                formData.append('file', file);

                const { data } = await apiClient.post('/ai/documents/upload', formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data',
                    },
                });

                console.log('Document uploaded:', data);
                await loadDocuments();
            } catch (error) {
                console.error('Upload failed:', error);
            }
        }

        setUploading(false);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const handleSearch = async () => {
        if (!searchQuery.trim()) {
            setSearchResults([]);
            return;
        }

        setSearching(true);
        try {
            const { data } = await apiClient.post('/ai/documents/search', null, {
                params: {
                    query: searchQuery,
                    top_k: 5
                }
            });
            setSearchResults(data);
        } catch (error) {
            console.error('Search failed:', error);
        } finally {
            setSearching(false);
        }
    };

    const handleDelete = async (id: string) => {
        if (window.confirm('Are you sure you want to delete this document?')) {
            try {
                await apiClient.delete(`/ai/documents/${id}`);
                await loadDocuments();
            } catch (error) {
                console.error('Delete failed:', error);
            }
        }
    };

    const formatFileSize = (sizeStr?: string) => {
        if (!sizeStr) return 'Unknown';
        const bytes = parseInt(sizeStr);
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        });
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case 'processing':
                return (
                    <span className="status-badge processing">
                        <Loader className="spin" size={14} />
                        Processing
                    </span>
                );
            case 'completed':
                return <span className="status-badge ready">● Ready</span>;
            case 'failed':
                return <span className="status-badge failed">✕ Failed</span>;
            default:
                return null;
        }
    };

    return (
        <div className="knowledge-base">
            <div className="page-header">
                <div>
                    <h1>Knowledge Base</h1>
                    <p>Upload documents for AI agents to reference using RAG</p>
                </div>
            </div>

            <GlassCard className="upload-section">
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.docx,.txt"
                    multiple
                    onChange={handleFileSelect}
                    style={{ display: 'none' }}
                />

                <div className="upload-area" onClick={() => fileInputRef.current?.click()}>
                    <Upload size={48} color="var(--color-accent-primary)" />
                    <h3>Upload Documents</h3>
                    <p>Click to select files or drag and drop</p>
                    <span className="file-types">Supports PDF, DOCX, TXT</span>
                </div>

                {uploading && (
                    <div className="upload-progress">
                        <Loader className="spin" size={24} />
                        <span>Processing documents...</span>
                    </div>
                )}
            </GlassCard>

            <GlassCard className="search-section">
                <h2>Search Documents</h2>
                <div className="search-bar">
                    <input
                        type="text"
                        placeholder="Search across all documents using semantic search..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                    />
                    <JellyButton onClick={handleSearch} disabled={searching}>
                        {searching ? <Loader className="spin" size={16} /> : <Search size={16} />}
                        Search
                    </JellyButton>
                </div>

                {searchResults.length > 0 && (
                    <div className="search-results">
                        <h3>Search Results ({searchResults.length})</h3>
                        {searchResults.map((result) => (
                            <div key={result.chunk_id} className="search-result-card">
                                <div className="result-header">
                                    <FileText size={16} />
                                    <span className="result-filename">{result.filename}</span>
                                    <span className="result-similarity">
                                        {(result.similarity * 100).toFixed(1)}% match
                                    </span>
                                </div>
                                <p className="result-content">{result.content}</p>
                            </div>
                        ))}
                    </div>
                )}
            </GlassCard>

            <div className="documents-section">
                <h2>Documents ({documents.length})</h2>

                {loading ? (
                    <GlassCard className="empty-state">
                        <Loader className="spin" size={64} />
                        <h3>Loading documents...</h3>
                    </GlassCard>
                ) : documents.length === 0 ? (
                    <GlassCard className="empty-state">
                        <FileText size={64} color="var(--color-text-tertiary)" />
                        <h3>No documents yet</h3>
                        <p>Upload your first document to get started</p>
                    </GlassCard>
                ) : (
                    <div className="documents-list">
                        {documents.map((doc) => (
                            <GlassCard key={doc.id} hover className="document-card">
                                <div className="document-icon">
                                    <FileText size={24} />
                                </div>

                                <div className="document-info">
                                    <h4>{doc.filename}</h4>
                                    <div className="document-meta">
                                        <span>{formatFileSize(doc.file_size)}</span>
                                        <span>•</span>
                                        <span>{formatDate(doc.created_at)}</span>
                                    </div>
                                </div>

                                <div className="document-status">
                                    {getStatusBadge(doc.upload_status)}
                                </div>

                                <JellyButton
                                    variant="ghost"
                                    onClick={() => handleDelete(doc.id)}
                                >
                                    <Trash2 size={16} />
                                </JellyButton>
                            </GlassCard>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
