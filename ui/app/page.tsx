'use client'

import { useState } from 'react'

interface Chunk {
  doc_title: string
  page_number: number
  doc_type: string
  text: string
  rerank_score: number
}

interface Citation {
  doc_id: string
  doc_title: string
  page_number: number
  doc_type: string
  section_ref: string
}

interface AnswerResponse {
  query: string
  rewritten_query: string
  answer: string
  citations: Citation[]
  is_refused: boolean
  tokens_used: number
  chunks_used: number
  top_chunks: Chunk[]
  response_time_ms: number
}

const DOC_TYPE_COLORS: Record<string, string> = {
  act: 'bg-blue-100 text-blue-800',
  judgment: 'bg-purple-100 text-purple-800',
  pov: 'bg-green-100 text-green-800',
  tax: 'bg-orange-100 text-orange-800',
}

export default function Home() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnswerResponse | null>(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'answer' | 'chunks'>('answer')

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setResult(null)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 50000)

    try {
      const res = await fetch('http://127.0.0.1:8000/api/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
        signal: controller.signal
      })
      clearTimeout(timeoutId)
      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || `API error: ${res.status}`)
      }
      const data = await res.json()
      setResult(data)
      setActiveTab('answer')
    } catch (err: unknown) {
      clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        setError('Request timed out - Groq rate limited. Try again in 60 seconds.')
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  const SAMPLE_QUERIES = [
    "What is gross income under IRC Section 61?",
    "How did the court define ordinary expense in Welch v Helvering?",
    "What are the requirements for tax exempt status under 501(c)(3)?",
    "What is the penalty rate under IRC Section 6662?",
  ]

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">⚖</span>
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Legal RAG</h1>
              <p className="text-xs text-gray-500">US Tax Law Research Assistant</p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full"></span>
              <span className="text-xs text-gray-500">3,497 chunks indexed</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Search Box */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Ask a US Tax Law Question
          </label>
          <div className="flex gap-3">
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. What are ordinary and necessary business expenses under IRC 162?"
              className="flex-1 border border-gray-300 rounded-lg px-4 py-3 text-sm 
                         focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              rows={2}
            />
            <button
              onClick={handleSearch}
              disabled={loading || !query.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium text-sm
                         hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors whitespace-nowrap"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>

          {/* Sample queries */}
          <div className="mt-3">
            <p className="text-xs text-gray-400 mb-2">Try these:</p>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUERIES.map((q, i) => (
                <button
                  key={i}
                  onClick={() => setQuery(q)}
                  className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 
                             px-3 py-1 rounded-full transition-colors"
                >
                  {q.length > 50 ? q.slice(0, 50) + '...' : q}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-700 text-sm font-medium">⚠️ {error}</p>
            {error.includes('rate limited') && (
              <p className="text-red-500 text-xs mt-1">
                All Groq API keys exhausted. Please wait 60 seconds and try again.
              </p>
            )}
            {error.includes('fetch') && (
              <p className="text-red-500 text-xs mt-1">
                Cannot connect to API. Make sure FastAPI is running on port 8000.
              </p>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center">
            <div className="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent 
                            rounded-full mx-auto mb-4"></div>
            <p className="text-gray-500 text-sm">Searching 3,497 legal chunks...</p>
            <p className="text-gray-400 text-xs mt-1">Hybrid BM25 + Vector → Rerank → Generate</p>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-4">
            {/* Meta info */}
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span>Rewritten: <em className="text-gray-700">{result.rewritten_query}</em></span>
              <span>•</span>
              <span>{result.response_time_ms}ms</span>
              <span>•</span>
              <span>{result.tokens_used} tokens</span>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b border-gray-200">
              {(['answer', 'chunks'] as const).map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 text-sm font-medium capitalize transition-colors
                    ${activeTab === tab
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-gray-500 hover:text-gray-700'
                    }`}
                >
                  {tab === 'answer' ? 'Answer' : `Sources (${result.top_chunks.length})`}
                </button>
              ))}
            </div>

            {/* Answer Tab */}
            {activeTab === 'answer' && (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                {result.is_refused ? (
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">⚠️</span>
                    <div>
                      <p className="font-medium text-gray-900 mb-1">
                        Insufficient Context
                      </p>
                      <p className="text-gray-600 text-sm">{result.answer}</p>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="prose prose-sm max-w-none text-gray-800 leading-relaxed whitespace-pre-wrap mb-6">
                      {result.answer}
                    </div>

                    {/* Citations */}
                    {result.citations.length > 0 && (
                      <div className="border-t border-gray-100 pt-4">
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                          Sources Cited
                        </p>
                        <div className="space-y-2">
                          {result.citations.map((c, i) => (
                            <div key={i}
                              className="flex items-center gap-3 p-3 bg-gray-50 
                                         rounded-lg border border-gray-100">
                              <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                                ${DOC_TYPE_COLORS[c.doc_type] || 'bg-gray-100 text-gray-600'}`}>
                                {c.doc_type}
                              </span>
                              <span className="text-sm text-gray-800 font-medium flex-1">
                                {c.doc_title}
                              </span>
                              <span className="text-xs text-gray-500 bg-white border 
                                               border-gray-200 px-2 py-0.5 rounded">
                                p.{c.page_number}
                              </span>
                              {c.section_ref && (
                                <span className="text-xs text-blue-600 font-mono">
                                  {c.section_ref}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Chunks Tab */}
            {activeTab === 'chunks' && (
              <div className="space-y-3">
                {result.top_chunks.map((chunk, i) => (
                  <div key={i}
                    className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                    <div className="flex items-center gap-3 mb-3">
                      <span className="text-xs font-bold text-gray-400">#{i + 1}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                        ${DOC_TYPE_COLORS[chunk.doc_type] || 'bg-gray-100 text-gray-600'}`}>
                        {chunk.doc_type}
                      </span>
                      <span className="text-sm font-medium text-gray-900 flex-1">
                        {chunk.doc_title}
                      </span>
                      <span className="text-xs text-gray-500 bg-gray-50 border 
                                       border-gray-200 px-2 py-0.5 rounded">
                        p.{chunk.page_number}
                      </span>
                      <span className="text-xs text-green-600 font-medium">
                        {(chunk.rerank_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 leading-relaxed">
                      {chunk.text}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!result && !loading && !error && (
          <div className="text-center py-16">
            <div className="text-5xl mb-4">⚖️</div>
            <h2 className="text-xl font-semibold text-gray-700 mb-2">
              US Tax Law Research
            </h2>
            <p className="text-gray-500 text-sm max-w-md mx-auto">
              Ask questions about IRC sections, court judgments, IRS publications,
              and tax policy. Every answer includes citations with page numbers.
            </p>
          </div>
        )}
      </div>
    </main>
  )
}