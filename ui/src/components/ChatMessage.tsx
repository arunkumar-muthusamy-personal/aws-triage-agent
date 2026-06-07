import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Message } from '../types'
import { EvidenceTrail } from './EvidenceTrail'

interface Props {
  message: Message
}

export function ChatMessage({ message }: Props) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (message.role === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[70%] bg-blue-600 text-white rounded-lg px-4 py-3 text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    )
  }

  if (message.role === 'error') {
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-[80%] bg-red-900 text-red-300 rounded-lg px-4 py-3 text-sm leading-relaxed">
          <span className="font-semibold">Error: </span>
          {message.content}
        </div>
      </div>
    )
  }

  // assistant
  return (
    <div className="flex justify-start mb-4 group">
      <div className="max-w-[80%] bg-gray-800 text-gray-100 rounded-lg px-4 py-3 text-sm leading-relaxed relative">
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>

        {message.isStreaming && (
          <span className="cursor-blink" aria-label="streaming" />
        )}

        {!message.isStreaming && message.content && (
          <button
            onClick={() => void handleCopy()}
            className="absolute top-2 right-2 text-xs text-gray-500 hover:text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity bg-gray-700 rounded px-2 py-1"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        )}

        {message.toolEvents.length > 0 && (
          <EvidenceTrail toolEvents={message.toolEvents} />
        )}
      </div>
    </div>
  )
}
