import { useState, useEffect, useCallback } from 'react'
import ConversationCard from './ConversationCard'
import { fetchAllConversations, markAllRead, summarizeAll } from '../middleware/api'
import '../styles/SummaryPanel.css'

interface Message {
    from: string
    text: string
    timestamp: number
}

interface Summary {
    who: string
    intent: string
    requirements: string[]
    urgency: string
    sentiment: string
    action_items: string[]
    one_liner: string
}

interface Conversation {
    sender: string
    conversation_id: string
    started_at: number
    last_activity: number
    messages: Message[]
    read: boolean
    summary: Summary | null
}

function SummaryPanel() {
    const [conversations, setConversations] = useState<Conversation[]>([])
    const [unreadCount, setUnreadCount] = useState(0)
    const [loading, setLoading] = useState(true)
    const [summarizingAll, setSummarizingAll] = useState(false)

    const loadConversations = useCallback(async () => {
        try {
            const data = await fetchAllConversations()
            const sorted = (data.conversations || []).sort(
                (a: Conversation, b: Conversation) => b.last_activity - a.last_activity
            )
            setConversations(sorted)
            setUnreadCount(data.unread_count || 0)
        } catch (err) {
            console.error('Failed to load conversations:', err)
        }
        setLoading(false)
    }, [])

    useEffect(() => {
        loadConversations()
        const interval = setInterval(loadConversations, 8000)
        return () => clearInterval(interval)
    }, [loadConversations])

    const handleClose = () => {
        if (window.electronAPI) {
            window.electronAPI.closeSummary()
        }
    }

    const handleMarkAllRead = async () => {
        await markAllRead()
        loadConversations()
    }

    const handleSummarizeAll = async () => {
        setSummarizingAll(true)
        try {
            await summarizeAll()
            await loadConversations()
        } catch (err) {
            console.error('Failed to summarize all:', err)
        }
        setSummarizingAll(false)
    }

    return (
        <div className="summary-panel">
            <div className="summary-panel__header">
                <div className="summary-panel__title-row">
                    <div className="summary-panel__icon">🐰</div>
                    <h2 className="summary-panel__title">TamaBotchi Inbox</h2>
                    {unreadCount > 0 && (
                        <span className="summary-panel__badge">{unreadCount}</span>
                    )}
                </div>
                <button className="summary-panel__close" onClick={handleClose}>✕</button>
            </div>

            <div className="summary-panel__actions">
                <button
                    className="summary-panel__btn summary-panel__btn--secondary"
                    onClick={handleMarkAllRead}
                    disabled={unreadCount === 0}
                >
                    Mark All Read
                </button>
                <button
                    className="summary-panel__btn summary-panel__btn--primary"
                    onClick={handleSummarizeAll}
                    disabled={summarizingAll || conversations.length === 0}
                >
                    {summarizingAll ? 'Summarizing...' : 'Summarize All'}
                </button>
            </div>

            <div className="summary-panel__list">
                {loading && (
                    <div className="summary-panel__empty">
                        <div className="summary-panel__loader" />
                        <p>Loading conversations...</p>
                    </div>
                )}

                {!loading && conversations.length === 0 && (
                    <div className="summary-panel__empty">
                        <div className="summary-panel__empty-icon">💤</div>
                        <p>No conversations yet</p>
                        <span>When someone messages you while on Do Not Disturb, the bunny will let you know!</span>
                    </div>
                )}

                {conversations.map((convo) => (
                    <ConversationCard
                        key={convo.conversation_id}
                        conversation={convo}
                        onRead={loadConversations}
                    />
                ))}
            </div>

            <div className="summary-panel__footer">
                <span>Powered by TamaBotchi AI Agent</span>
            </div>
        </div>
    )
}

export default SummaryPanel
