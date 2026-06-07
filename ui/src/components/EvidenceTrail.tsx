import { useState } from 'react'
import { ToolEvent } from '../types'

interface Props {
  toolEvents: ToolEvent[]
}

function truncate(str: string, max = 500): string {
  return str.length > max ? str.slice(0, max) + '…' : str
}

export function EvidenceTrail({ toolEvents }: Props) {
  const [open, setOpen] = useState(false)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  if (toolEvents.length === 0) return null

  // Count unique tool calls (tool_start events)
  const toolCount = toolEvents.filter((e) => e.type === 'tool_start').length

  return (
    <div className="mt-2 border-l-2 border-blue-500 pl-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1"
      >
        <span>{open ? '▼' : '▶'}</span>
        <span>Evidence Trail ({toolCount} tool call{toolCount !== 1 ? 's' : ''})</span>
      </button>

      {open && (
        <div className="mt-1 space-y-1">
          {toolEvents
            .filter((e) => e.type === 'tool_start')
            .map((event, idx) => {
              const hasDuration = event.duration_ms !== undefined
              const isPending = !hasDuration && event.output === undefined

              return (
                <div key={idx}>
                  <button
                    onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
                    className="w-full text-left text-xs text-gray-400 hover:text-gray-200 transition-colors font-mono"
                  >
                    <span className="text-gray-600">├─ </span>
                    <span className="text-blue-400">{event.tool}</span>
                    <span className="text-gray-500"> → </span>
                    {isPending ? (
                      <span className="text-yellow-500">...</span>
                    ) : (
                      <span className="text-green-500">
                        done
                        {hasDuration && (
                          <span className="text-gray-500 ml-1">({event.duration_ms}ms)</span>
                        )}
                      </span>
                    )}
                  </button>

                  {expandedIdx === idx && (
                    <div className="mt-1 ml-4 bg-gray-900 rounded p-2">
                      {event.input && (
                        <div>
                          <div className="text-xs text-gray-500 mb-1">Input:</div>
                          <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all">
                            {truncate(JSON.stringify(event.input, null, 2))}
                          </pre>
                        </div>
                      )}
                      {event.output && (
                        <div className="mt-2">
                          <div className="text-xs text-gray-500 mb-1">Output:</div>
                          <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all">
                            {truncate(JSON.stringify(event.output, null, 2))}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
        </div>
      )}
    </div>
  )
}
