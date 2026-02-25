import React, { useState, useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { GlassCard } from '@/components/ui';
import './PhoneNumbersPage.css';

// Helper function to generate UUID (compatible with all browsers)
const generateUUID = (): string => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback for browsers that don't support crypto.randomUUID
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

interface PhoneNumber {
    id: string;
    customer_id: string;
    customer_name: string;
    phone_number: string;
    provider: string;
    agent_id: string;
    agent_name: string;
    is_active: boolean;
    assigned_at: string;
}

interface Agent {
    id: string;
    name: string;
}

interface Customer {
    id: string;
    name: string;
    company_name?: string;
}

export const PhoneNumbersPage: React.FC = () => {
    const { token } = useAuth();
    const [phoneNumbers, setPhoneNumbers] = useState<PhoneNumber[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        customer_name: '',
        phone_number: '',
        provider: 'twilio',
        agent_id: '',
        customer_id: ''
    });

    useEffect(() => {
        fetchPhoneNumbers();
        fetchAgents();
        fetchCustomers();
    }, []);

    const fetchPhoneNumbers = async () => {
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/phone-numbers`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            const data = await response.json();
            setPhoneNumbers(data.phone_numbers || []);
        } catch (error) {
            console.error('Error fetching phone numbers:', error);
        } finally {
            setLoading(false);
        }
    };

    const fetchAgents = async () => {
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/ai/entities?entity_type=AGENT`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                console.error('Failed to fetch agents:', response.status, response.statusText);
                return;
            }

            const data = await response.json();
            console.log('Agents response:', data);

            // Handle different possible response structures
            if (Array.isArray(data)) {
                setAgents(data);
            } else if (data.entities && Array.isArray(data.entities)) {
                setAgents(data.entities);
            } else if (data.data && Array.isArray(data.data)) {
                setAgents(data.data);
            } else {
                console.warn('Unexpected agents response structure:', data);
            }
        } catch (error) {
            console.error('Error fetching agents:', error);
        }
    };

    const fetchCustomers = async () => {
        try {
            // Fetch tenants from the correct endpoint
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/companies/tenants`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Failed to fetch customers:', response.status, response.statusText);
                console.error('Error details:', errorText);

                // If 403/401, user doesn't have permission to view tenants - that's okay
                if (response.status === 403 || response.status === 401) {
                    console.warn('User does not have permission to view tenants. Customer name must be entered manually.');
                }
                return;
            }

            const data = await response.json();
            console.log('Customers response:', data);

            // Handle different possible response structures
            if (Array.isArray(data)) {
                setCustomers(data);
                console.log(`Loaded ${data.length} customers`);
            } else if (data.tenants && Array.isArray(data.tenants)) {
                const mappedCustomers = data.tenants.map((t: any) => ({
                    id: t.id,
                    name: t.name,
                    company_name: t.company_name
                }));
                setCustomers(mappedCustomers);
                console.log(`Loaded ${mappedCustomers.length} customers from tenants`);
            } else if (data.data && Array.isArray(data.data)) {
                setCustomers(data.data);
                console.log(`Loaded ${data.data.length} customers from data`);
            } else {
                console.warn('Unexpected customer response structure:', data);
            }
        } catch (error) {
            console.error('Error fetching customers:', error);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        // Ensure we have either customer_id or customer_name
        if (!formData.customer_id && !formData.customer_name) {
            alert('Please select a customer or enter a customer name');
            return;
        }

        try {
            const submitData = {
                ...formData,
                customer_id: formData.customer_id || generateUUID(),
                customer_name: formData.customer_name || 'Unknown Customer'
            };

            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/phone-numbers`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(submitData)
            });

            if (response.ok) {
                setShowModal(false);
                setFormData({
                    customer_name: '',
                    phone_number: '',
                    provider: 'twilio',
                    agent_id: '',
                    customer_id: ''
                });
                fetchPhoneNumbers();
            } else {
                const error = await response.json();
                alert(`Error: ${error.detail}`);
            }
        } catch (error) {
            console.error('Error creating phone number:', error);
            alert('Failed to create phone number assignment');
        }
    };

    const handleToggleActive = async (id: string, currentStatus: boolean) => {
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/phone-numbers/${id}`, {
                method: 'PATCH',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    is_active: !currentStatus
                })
            });

            if (response.ok) {
                fetchPhoneNumbers();
            }
        } catch (error) {
            console.error('Error updating phone number:', error);
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Are you sure you want to delete this phone number assignment?')) {
            return;
        }

        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/phone-numbers/${id}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                fetchPhoneNumbers();
            }
        } catch (error) {
            console.error('Error deleting phone number:', error);
        }
    };

    if (loading) {
        return <div className="loading">Loading phone numbers...</div>;
    }

    return (
        <div className="phone-numbers-page">
            <div className="page-header">
                <div>
                    <h1>Customer Phone Numbers</h1>
                    <p className="subtitle">Manage phone number assignments for voice and WhatsApp</p>
                </div>
                <button className="btn-primary" onClick={() => setShowModal(true)}>
                    + Add Phone Number
                </button>
            </div>

            <GlassCard>
                <div className="phone-numbers-grid">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Customer Name</th>
                                <th>Phone Number</th>
                                <th>Provider</th>
                                <th>Agent</th>
                                <th>Status</th>
                                <th>Assigned</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {phoneNumbers.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="empty-state">
                                        No phone numbers configured. Add one to get started.
                                    </td>
                                </tr>
                            ) : (
                                phoneNumbers.map(pn => (
                                    <tr key={pn.id}>
                                        <td>{pn.customer_name}</td>
                                        <td className="phone-number">{pn.phone_number}</td>
                                        <td>
                                            <span className={`provider-badge ${pn.provider}`}>
                                                {pn.provider === 'twilio' ? 'Twilio' : 'Tata Tele'}
                                            </span>
                                        </td>
                                        <td>{pn.agent_name}</td>
                                        <td>
                                            <span className={`status-badge ${pn.is_active ? 'active' : 'inactive'}`}>
                                                {pn.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td>{new Date(pn.assigned_at).toLocaleDateString()}</td>
                                        <td className="actions">
                                            <button
                                                className="btn-icon"
                                                onClick={() => handleToggleActive(pn.id, pn.is_active)}
                                                title={pn.is_active ? 'Deactivate' : 'Activate'}
                                            >
                                                {pn.is_active ? '⏸' : '▶'}
                                            </button>
                                            <button
                                                className="btn-icon danger"
                                                onClick={() => handleDelete(pn.id)}
                                                title="Delete"
                                            >
                                                🗑
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </GlassCard>

            {showModal && (
                <div className="modal-overlay" onClick={() => setShowModal(false)}>
                    <div className="modal-content" onClick={e => e.stopPropagation()}>
                        <h2>Add Phone Number Assignment</h2>
                        <form onSubmit={handleSubmit}>
                            {customers.length > 0 && (
                                <div className="form-group">
                                    <label>Select Existing Customer (Optional)</label>
                                    <select
                                        value={formData.customer_id}
                                        onChange={e => {
                                            const selectedCustomer = customers.find(c => c.id === e.target.value);
                                            if (selectedCustomer) {
                                                setFormData({
                                                    ...formData,
                                                    customer_id: e.target.value,
                                                    customer_name: selectedCustomer?.name || selectedCustomer?.company_name || ''
                                                });
                                            } else {
                                                setFormData({
                                                    ...formData,
                                                    customer_id: '',
                                                    customer_name: ''
                                                });
                                            }
                                        }}
                                    >
                                        <option value="">-- Or enter new customer below --</option>
                                        {customers.map(customer => (
                                            <option key={customer.id} value={customer.id}>
                                                {customer.company_name || customer.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            )}

                            <div className="form-group">
                                <label>Customer Name {customers.length > 0 ? '(or enter new)' : ''}</label>
                                <input
                                    type="text"
                                    value={formData.customer_name}
                                    onChange={e => setFormData({ ...formData, customer_name: e.target.value, customer_id: '' })}
                                    placeholder="Enter customer name"
                                    required={!formData.customer_id}
                                />
                                <small style={{ color: 'var(--text-secondary)', marginTop: '0.25rem', display: 'block', fontSize: '0.875rem' }}>
                                    {formData.customer_id ? 'Selected from dropdown above' : 'Enter the customer or company name'}
                                </small>
                            </div>

                            <div className="form-group">
                                <label>Phone Number</label>
                                <input
                                    type="tel"
                                    value={formData.phone_number}
                                    onChange={e => setFormData({ ...formData, phone_number: e.target.value })}
                                    placeholder="+1234567890"
                                    required
                                />
                            </div>

                            <div className="form-group">
                                <label>Provider</label>
                                <select
                                    value={formData.provider}
                                    onChange={e => setFormData({ ...formData, provider: e.target.value })}
                                    required
                                >
                                    <option value="twilio">Twilio</option>
                                    <option value="tata_tele">Tata Tele</option>
                                </select>
                            </div>

                            <div className="form-group">
                                <label>Agent</label>
                                <select
                                    value={formData.agent_id}
                                    onChange={e => setFormData({ ...formData, agent_id: e.target.value })}
                                    required
                                >
                                    <option value="">Select an agent...</option>
                                    {agents.map(agent => (
                                        <option key={agent.id} value={agent.id}>
                                            {agent.name}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="form-actions">
                                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn-primary">
                                    Add Phone Number
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
