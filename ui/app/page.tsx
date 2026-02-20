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
  cited_title?: string
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

const DOC_TYPE_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  act: { label: 'STATUTE', color: '#1565C0', bg: '#E3F2FD', border: '#1565C0' },
  judgment: { label: 'CASE LAW', color: '#4A148C', bg: '#F3E5F5', border: '#4A148C' },
  pov: { label: 'ANALYSIS', color: '#1B5E20', bg: '#E8F5E9', border: '#1B5E20' },
  tax: { label: 'IRS PUB', color: '#E65100', bg: '#FFF3E0', border: '#E65100' },
}

const SAMPLE_QUERIES = [
  "What is gross income under IRC Section 61?",
  "How did the court define ordinary expense in Welch v Helvering?",
  "What are the requirements for tax exempt status under 501(c)(3)?",
  "What is the penalty rate under IRC Section 6662?",
  "What are the like-kind exchange rules under IRC Section 1031?",
  "How does the IRC define capital assets under Section 1221?",
]

export default function Home() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnswerResponse | null>(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'answer' | 'sources'>('answer')
  const [activeNav, setActiveNav] = useState('search')

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setResult(null)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 50000)

    try {
      const res = await fetch('http://127.0.0.1:8001/api/answer', {
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
        setError('Request timed out. Groq API rate limited â€” please wait 60 seconds and retry.')
      } else {
        setError(err instanceof Error ? err.message : 'Connection failed.')
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

  return (
    <div style={{ fontFamily: "'Georgia', 'Times New Roman', serif", minHeight: '100vh', background: '#F4F6F9' }}>

      {/* TOP BANNER */}
      <div style={{ background: '#0D2137', color: '#fff', padding: '6px 0', textAlign: 'center', fontSize: '11px', letterSpacing: '0.5px' }}>
        OFFICIAL US TAX LAW RESEARCH SYSTEM &nbsp;|&nbsp; FOR LEGAL PROFESSIONAL USE ONLY
      </div>

      {/* HEADER */}
      <header style={{ background: '#0A3055', borderBottom: '4px solid #C8A951', padding: '0' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '16px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            {/* Seal */}
            <div style={{
              width: '56px', height: '56px', borderRadius: '50%',
              background: '#C8A951', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: '24px', flexShrink: 0,
              border: '3px solid #fff'
            }}>âš–</div>
            <div>
              <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#FFFFFF', letterSpacing: '0.5px' }}>
                Legal RAG System
              </div>
              <div style={{ fontSize: '12px', color: '#C8A951', letterSpacing: '1px', marginTop: '2px' }}>
                US TAX LAW RESEARCH ASSISTANT &nbsp;Â·&nbsp; AI-POWERED CITATION ENGINE
              </div>
            </div>
          </div>
          {/* Status badges */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <span style={{ background: '#1B5E20', color: '#fff', padding: '3px 10px', borderRadius: '3px', fontSize: '11px', fontFamily: 'monospace' }}>
                â— ES CONNECTED
              </span>
              <span style={{ background: '#1565C0', color: '#fff', padding: '3px 10px', borderRadius: '3px', fontSize: '11px', fontFamily: 'monospace' }}>
                3,497 CHUNKS INDEXED
              </span>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <span style={{ background: '#33333380', color: '#ccc', padding: '3px 10px', borderRadius: '3px', fontSize: '11px', fontFamily: 'monospace' }}>
                101 DOCUMENTS Â· 4 PILLARS
              </span>
            </div>
          </div>
        </div>

        {/* NAV BAR */}
        <div style={{ background: '#0C3A62', borderTop: '1px solid #1a5276' }}>
          <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 24px', display: 'flex', gap: '0' }}>
            {[
              { label: 'Search & Query', key: 'search' },
              { label: 'IRC Statutes',   key: 'irc' },
              { label: 'Case Law',       key: 'cases' },
              { label: 'IRS Publications', key: 'irs' },
              { label: 'About',          key: 'about' },
            ].map((item) => (
              <div
                key={item.key}
                onClick={() => setActiveNav(item.key)}
                style={{
                  padding: '10px 18px', fontSize: '12px',
                  color: activeNav === item.key ? '#C8A951' : '#9ab',
                  borderBottom: activeNav === item.key ? '3px solid #C8A951' : '3px solid transparent',
                  cursor: 'pointer', letterSpacing: '0.3px', fontFamily: 'sans-serif'
                }}
              >
                {item.label}
              </div>
            ))}
          </div>
        </div>
      </header>

      {/* BREADCRUMB */}
      <div style={{ background: '#E8EDF2', borderBottom: '1px solid #CBD5E0', padding: '8px 0' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 24px', fontSize: '11px', color: '#555', fontFamily: 'sans-serif' }}>
          Home &rsaquo; Search &rsaquo; Tax Law Query
        </div>
      </div>

      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '24px' }}>

          {/* LEFT SIDEBAR */}
          <div>
            {/* Search Panel */}
            <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #0A3055', marginBottom: '16px' }}>
              <div style={{ background: '#0A3055', color: '#fff', padding: '10px 14px', fontSize: '12px', fontWeight: 'bold', letterSpacing: '0.5px', fontFamily: 'sans-serif' }}>
                LEGAL RESEARCH QUERY
              </div>
              <div style={{ padding: '14px' }}>
                <div style={{ fontSize: '11px', color: '#555', marginBottom: '6px', fontFamily: 'sans-serif' }}>
                  Enter your tax law question:
                </div>
                <textarea
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="e.g. What are ordinary and necessary business expenses under IRC 162?"
                  style={{
                    width: '100%', border: '1px solid #9ab', borderRadius: '2px',
                    padding: '8px', fontSize: '12px', resize: 'none', minHeight: '80px',
                    fontFamily: 'sans-serif', boxSizing: 'border-box', outline: 'none',
                    color: '#000000', background: '#FFFFFF'
                  }}
                />
                <button
                  onClick={handleSearch}
                  disabled={loading || !query.trim()}
                  style={{
                    width: '100%', marginTop: '8px', padding: '10px',
                    background: loading ? '#666' : '#0A3055',
                    color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
                    fontSize: '12px', fontWeight: 'bold', letterSpacing: '1px',
                    fontFamily: 'sans-serif'
                  }}
                >
                  {loading ? 'SEARCHING...' : 'SUBMIT QUERY'}
                </button>
              </div>
            </div>

            {/* Document Types */}
            <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #0A3055', marginBottom: '16px' }}>
              <div style={{ background: '#0A3055', color: '#fff', padding: '10px 14px', fontSize: '12px', fontWeight: 'bold', letterSpacing: '0.5px', fontFamily: 'sans-serif' }}>
                DOCUMENT CORPUS
              </div>
              <div style={{ padding: '14px' }}>
                {[
                  { type: 'act', label: 'IRC Statutes', count: 30, icon: 'Â§' },
                  { type: 'judgment', label: 'Court Judgments', count: 30, icon: 'âš–' },
                  { type: 'pov', label: 'POV / Commentary', count: 30, icon: 'ðŸ“‹' },
                  { type: 'tax', label: 'IRS Publications', count: 10, icon: 'ðŸ“„' },
                ].map((item) => {
                  const cfg = DOC_TYPE_CONFIG[item.type]
                  return (
                    <div key={item.type} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '7px 10px', marginBottom: '6px', background: cfg.bg,
                      border: `1px solid ${cfg.border}`, borderLeft: `4px solid ${cfg.border}`,
                      borderRadius: '2px'
                    }}>
                      <div style={{ fontSize: '12px', color: cfg.color, fontWeight: 'bold', fontFamily: 'sans-serif' }}>
                        {item.icon} {item.label}
                      </div>
                      <div style={{ fontSize: '11px', color: cfg.color, fontFamily: 'monospace', background: '#fff', padding: '1px 6px', border: `1px solid ${cfg.border}` }}>
                        {item.count}
                      </div>
                    </div>
                  )
                })}
                <div style={{ marginTop: '10px', padding: '6px', background: '#F4F6F9', border: '1px solid #CBD5E0', textAlign: 'center' }}>
                  <span style={{ fontSize: '11px', color: '#555', fontFamily: 'monospace' }}>TOTAL: 101 DOCUMENTS</span>
                </div>
              </div>
            </div>

            {/* Sample Queries */}
            <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #C8A951' }}>
              <div style={{ background: '#7B5E1A', color: '#fff', padding: '10px 14px', fontSize: '12px', fontWeight: 'bold', letterSpacing: '0.5px', fontFamily: 'sans-serif' }}>
                SAMPLE QUERIES
              </div>
              <div style={{ padding: '10px' }}>
                {SAMPLE_QUERIES.map((q, i) => (
                  <div
                    key={i}
                    onClick={() => setQuery(q)}
                    style={{
                      padding: '7px 10px', marginBottom: '5px', fontSize: '11px',
                      color: '#0A3055', cursor: 'pointer', background: '#F4F6F9',
                      border: '1px solid #CBD5E0', borderLeft: '3px solid #0A3055',
                      fontFamily: 'sans-serif', lineHeight: '1.4'
                    }}
                  >
                    {q}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* MAIN CONTENT */}
          <div>

            {/* IRC Statutes Page */}
            {activeNav === 'irc' && (
              <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #1565C0', padding: '24px' }}>
                <h2 style={{ color: '#0A3055', fontSize: '16px', marginBottom: '16px', fontFamily: 'Georgia, serif' }}>IRC Statutes â€” Internal Revenue Code</h2>
                <p style={{ color: '#555', fontSize: '13px', lineHeight: '1.8', fontFamily: 'sans-serif', marginBottom: '16px' }}>
                  This system indexes <strong>30 IRC sections</strong> from Title 26 of the United States Code, sourced from GovInfo.gov.
                </p>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: 'sans-serif' }}>
                  <thead>
                    <tr style={{ background: '#0A3055', color: '#fff' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>SECTION</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>TITLE</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>TOPIC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Â§61',   'Gross Income Defined',          'Income Definition'],
                      ['Â§62',   'Adjusted Gross Income',          'Income Definition'],
                      ['Â§101',  'Life Insurance Exclusions',      'Exclusions'],
                      ['Â§102',  'Gifts and Inheritances',         'Exclusions'],
                      ['Â§121',  'Home Sale Exclusion',            'Exclusions'],
                      ['Â§162',  'Trade or Business Expenses',     'Deductions'],
                      ['Â§163',  'Interest Deduction',             'Deductions'],
                      ['Â§165',  'Losses',                         'Deductions'],
                      ['Â§167',  'Depreciation',                   'Deductions'],
                      ['Â§170',  'Charitable Contributions',       'Deductions'],
                      ['Â§183',  'Hobby Loss Rules',               'Deductions'],
                      ['Â§199A', 'Qualified Business Income',      'Deductions'],
                      ['Â§263',  'Capital Expenditures',           'Deductions'],
                      ['Â§351',  'Transfer to Corporation',        'Corporate'],
                      ['Â§368',  'Corporate Reorganizations',      'Corporate'],
                      ['Â§401',  'Qualified Pension Plans',        'Retirement'],
                      ['Â§408',  'Individual Retirement Accounts', 'Retirement'],
                      ['Â§501',  'Tax-Exempt Organizations',       'Exempt Orgs'],
                      ['Â§1001', 'Gain or Loss on Disposition',    'Capital Gains'],
                      ['Â§1031', 'Like-Kind Exchanges',            'Capital Gains'],
                      ['Â§1221', 'Capital Asset Defined',          'Capital Gains'],
                      ['Â§6662', 'Accuracy-Related Penalty',       'Penalties'],
                      ['Â§7201', 'Tax Evasion',                    'Criminal'],
                    ].map(([sec, title, topic], i) => (
                      <tr key={i}
                        style={{ background: i%2===0?'#F8F9FA':'#fff', borderBottom: '1px solid #E8EDF2', cursor: 'pointer' }}
                        onClick={() => { setQuery(`What does IRC ${sec} say about ${title}?`); setActiveNav('search') }}>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#1565C0', fontWeight: 'bold' }}>{sec}</td>
                        <td style={{ padding: '8px 12px', color: '#0A3055', fontWeight: 'bold' }}>{title}</td>
                        <td style={{ padding: '8px 12px', color: '#555' }}>{topic}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p style={{ fontSize: '11px', color: '#888', marginTop: '12px', fontFamily: 'sans-serif' }}>
                  Click any row to auto-fill the search query.
                </p>
              </div>
            )}

            {/* Case Law Page */}
            {activeNav === 'cases' && (
              <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #4A148C', padding: '24px' }}>
                <h2 style={{ color: '#0A3055', fontSize: '16px', marginBottom: '16px', fontFamily: 'Georgia, serif' }}>Case Law â€” Landmark Tax Court Judgments</h2>
                <p style={{ color: '#555', fontSize: '13px', lineHeight: '1.8', fontFamily: 'sans-serif', marginBottom: '16px' }}>
                  30 landmark US federal court decisions sourced from CourtListener API and Justia.
                </p>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: 'sans-serif' }}>
                  <thead>
                    <tr style={{ background: '#0A3055', color: '#fff' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>CASE</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>YEAR</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>IRC SECTION</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>KEY ISSUE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Commissioner v. Glenshaw Glass', '1955', 'Â§61',   'Punitive damages as gross income'],
                      ['Welch v. Helvering',             '1933', 'Â§162',  'Ordinary and necessary expenses'],
                      ['Bob Jones Univ. v. US',          '1983', 'Â§501',  'Public policy and tax exemption'],
                      ['Cheek v. United States',         '1991', 'Â§7201', 'Willfulness in tax evasion'],
                      ['Starker v. United States',       '1979', 'Â§1031', 'Like-kind exchange timing'],
                      ['INDOPCO v. Commissioner',        '1992', 'Â§162',  'Capital vs deductible expenses'],
                      ['Crane v. Commissioner',          '1947', 'Â§1001', 'Liabilities in basis calculation'],
                      ['Commissioner v. Tufts',          '1983', 'Â§1001', 'Nonrecourse liability on sale'],
                      ['Arkansas Best Corp. v. Comm.',   '1988', 'Â§1221', 'Capital asset definition'],
                      ['Cottage Savings v. Comm.',       '1991', 'Â§1001', 'Realization of gain or loss'],
                      ['Gregory v. Helvering',           '1935', 'Â§368',  'Substance over form doctrine'],
                      ['Hernandez v. Commissioner',      '1989', 'Â§170',  'Charitable contribution quid pro quo'],
                      ['Old Colony Trust v. Comm.',      '1929', 'Â§61',   'Payment by third party as income'],
                      ['Cesarini v. United States',      '1969', 'Â§61',   'Found money as gross income'],
                      ['Commissioner v. Duberstein',     '1960', 'Â§102',  'Gift vs income distinction'],
                    ].map(([case_, year, sec, issue], i) => (
                      <tr key={i}
                        style={{ background: i%2===0?'#F8F9FA':'#fff', borderBottom: '1px solid #E8EDF2', cursor: 'pointer' }}
                        onClick={() => { setQuery(`What did the court hold in ${case_}?`); setActiveNav('search') }}>
                        <td style={{ padding: '8px 12px', color: '#4A148C', fontWeight: 'bold' }}>{case_}</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#555' }}>{year}</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#1565C0' }}>{sec}</td>
                        <td style={{ padding: '8px 12px', color: '#333' }}>{issue}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p style={{ fontSize: '11px', color: '#888', marginTop: '12px', fontFamily: 'sans-serif' }}>
                  Click any row to auto-fill the search query.
                </p>
              </div>
            )}

            {/* IRS Publications Page */}
            {activeNav === 'irs' && (
              <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #E65100', padding: '24px' }}>
                <h2 style={{ color: '#0A3055', fontSize: '16px', marginBottom: '16px', fontFamily: 'Georgia, serif' }}>IRS Publications</h2>
                <p style={{ color: '#555', fontSize: '13px', lineHeight: '1.8', fontFamily: 'sans-serif', marginBottom: '16px' }}>
                  10 official IRS publications sourced directly from IRS.gov.
                </p>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: 'sans-serif' }}>
                  <thead>
                    <tr style={{ background: '#0A3055', color: '#fff' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>PUBLICATION</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>TITLE</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>TOPIC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Pub 17',    'Your Federal Income Tax',                'Individual Filing'],
                      ['Pub 334',   'Tax Guide for Small Business',           'Business Tax'],
                      ['Pub 463',   'Travel Gift and Car Expenses',           'Business Deductions'],
                      ['Pub 526',   'Charitable Contributions',               'Deductions'],
                      ['Pub 535',   'Business Expenses',                      'Deductions'],
                      ['Pub 544',   'Sales of Business Property',             'Capital Gains'],
                      ['Pub 550',   'Investment Income and Expenses',         'Investment Tax'],
                      ['Pub 590-A', 'Contributions to IRAs',                  'Retirement'],
                      ['Pub 946',   'How to Depreciate Property',             'Depreciation'],
                      ['Pub 15-B',  'Employers Tax Guide to Fringe Benefits', 'Employment Tax'],
                    ].map(([pub, title, topic], i) => (
                      <tr key={i}
                        style={{ background: i%2===0?'#F8F9FA':'#fff', borderBottom: '1px solid #E8EDF2', cursor: 'pointer' }}
                        onClick={() => { setQuery(`What does IRS ${pub} say about ${topic}?`); setActiveNav('search') }}>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#E65100', fontWeight: 'bold' }}>{pub}</td>
                        <td style={{ padding: '8px 12px', color: '#0A3055', fontWeight: 'bold' }}>{title}</td>
                        <td style={{ padding: '8px 12px', color: '#555' }}>{topic}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p style={{ fontSize: '11px', color: '#888', marginTop: '12px', fontFamily: 'sans-serif' }}>
                  Click any row to auto-fill the search query.
                </p>
              </div>
            )}

            {/* About Page */}
            {activeNav === 'about' && (
              <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #0A3055', padding: '24px' }}>
                <h2 style={{ color: '#0A3055', fontSize: '16px', marginBottom: '16px', fontFamily: 'Georgia, serif' }}>About This System</h2>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '16px', marginBottom: '24px' }}>
                  {[
                    { label: 'Total Documents', value: '101',     color: '#0A3055' },
                    { label: 'Total Chunks',    value: '3,497',   color: '#1565C0' },
                    { label: 'Embedding Dims',  value: '768',     color: '#4A148C' },
                    { label: 'Index Size',      value: '60.2 MB', color: '#1B5E20' },
                  ].map((item, i) => (
                    <div key={i} style={{ background: '#F4F6F9', border: '1px solid #CBD5E0', borderLeft: `4px solid ${item.color}`, padding: '16px' }}>
                      <div style={{ fontSize: '24px', fontWeight: 'bold', color: item.color, fontFamily: 'monospace' }}>{item.value}</div>
                      <div style={{ fontSize: '11px', color: '#555', fontFamily: 'sans-serif', marginTop: '4px' }}>{item.label}</div>
                    </div>
                  ))}
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: 'sans-serif' }}>
                  <thead>
                    <tr style={{ background: '#0A3055', color: '#fff' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>COMPONENT</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>TECHNOLOGY</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>PURPOSE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Parser',       'PyMuPDF',                'PDF text extraction with page index'],
                      ['Embeddings',   'BAAI/bge-base-en-v1.5',  'Dense vector generation (768 dims)'],
                      ['Search DB',    'Elasticsearch 8.13',      'BM25 + kNN hybrid search'],
                      ['Reranker',     'BAAI/bge-reranker-base',  'Cross-encoder reranking Top-8'],
                      ['Fusion',       'RRF k=60',                'Reciprocal Rank Fusion'],
                      ['Graph',        'NetworkX',                'Citation graph 72 edges'],
                      ['LLM',          'Groq LLaMA 3.3 70B',      'Grounded answer generation'],
                      ['Faithfulness', 'DeBERTa NLI',             'Answer verification'],
                      ['Frontend',     'Next.js',                 'User Interface'],
                      ['Backend',      'FastAPI + Uvicorn',        'REST API'],
                    ].map(([comp, tech, purpose], i) => (
                      <tr key={i} style={{ background: i%2===0?'#F8F9FA':'#fff', borderBottom: '1px solid #E8EDF2' }}>
                        <td style={{ padding: '8px 12px', fontWeight: 'bold', color: '#0A3055' }}>{comp}</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#1565C0' }}>{tech}</td>
                        <td style={{ padding: '8px 12px', color: '#555' }}>{purpose}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Search Page */}
            {activeNav === 'search' && (
              <>

            {/* Error */}
            {error && (
              <div style={{ background: '#FFEBEE', border: '1px solid #C62828', borderLeft: '4px solid #C62828', padding: '12px 16px', marginBottom: '16px', fontFamily: 'sans-serif' }}>
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#C62828', marginBottom: '4px' }}>
                  âš  SYSTEM NOTICE
                </div>
                <div style={{ fontSize: '12px', color: '#B71C1C' }}>{error}</div>
                {error.includes('rate limited') && (
                  <div style={{ fontSize: '11px', color: '#888', marginTop: '6px' }}>
                    All API keys exhausted. Please wait 60 seconds and resubmit.
                  </div>
                )}
              </div>
            )}

            {/* Loading */}
            {loading && (
              <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #0A3055', padding: '40px', textAlign: 'center' }}>
                <div style={{ fontSize: '32px', marginBottom: '16px' }}>âš–</div>
                <div style={{ fontSize: '14px', color: '#0A3055', fontWeight: 'bold', marginBottom: '8px', fontFamily: 'sans-serif' }}>
                  PROCESSING LEGAL QUERY
                </div>
                <div style={{ fontSize: '11px', color: '#666', fontFamily: 'monospace', lineHeight: '2' }}>
                  STEP 1: Query rewriting (Groq LLaMA 8B)<br />
                  STEP 2: Hybrid BM25 + Vector search (3,497 chunks)<br />
                  STEP 3: BGE Cross-Encoder reranking (Top-8)<br />
                  STEP 4: LLM generation with citations (Groq 70B)
                </div>
                <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'center', gap: '4px' }}>
                  {[0, 1, 2, 3, 4].map(i => (
                    <div key={i} style={{
                      width: '8px', height: '8px', borderRadius: '50%',
                      background: '#0A3055', animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`
                    }} />
                  ))}
                </div>
              </div>
            )}

            {/* Results */}
            {result && !loading && (
              <div>
                {/* Query info bar */}
                <div style={{ background: '#0A3055', color: '#fff', padding: '10px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontFamily: 'monospace', fontSize: '11px' }}>
                  <span>QUERY PROCESSED &nbsp;|&nbsp; {result.response_time_ms}ms &nbsp;|&nbsp; {result.tokens_used} TOKENS USED</span>
                  <span style={{ color: '#C8A951' }}>{result.chunks_used} CHUNKS RETRIEVED</span>
                </div>

                {/* Rewritten query */}
                <div style={{ background: '#EBF5FB', border: '1px solid #AED6F1', borderTop: 'none', padding: '8px 16px', fontFamily: 'sans-serif' }}>
                  <span style={{ fontSize: '10px', color: '#1565C0', fontWeight: 'bold', letterSpacing: '0.5px' }}>OPTIMIZED SEARCH TERMS: </span>
                  <span style={{ fontSize: '11px', color: '#1565C0', fontStyle: 'italic' }}>{result.rewritten_query}</span>
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', background: '#E8EDF2', borderBottom: '1px solid #CBD5E0', marginTop: '16px' }}>
                  {[
                    { key: 'answer', label: 'LEGAL ANALYSIS' },
                    { key: 'sources', label: `SOURCE DOCUMENTS (${result.top_chunks.length})` },
                  ].map(tab => (
                    <div
                      key={tab.key}
                      onClick={() => setActiveTab(tab.key as 'answer' | 'sources')}
                      style={{
                        padding: '10px 20px', fontSize: '11px', fontWeight: 'bold',
                        cursor: 'pointer', letterSpacing: '0.5px', fontFamily: 'sans-serif',
                        background: activeTab === tab.key ? '#fff' : 'transparent',
                        color: activeTab === tab.key ? '#0A3055' : '#666',
                        borderTop: activeTab === tab.key ? '3px solid #0A3055' : '3px solid transparent',
                        borderRight: '1px solid #CBD5E0'
                      }}
                    >
                      {tab.label}
                    </div>
                  ))}
                </div>

                {/* Answer Tab */}
                {activeTab === 'answer' && (
                  <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: 'none', padding: '24px' }}>

                    {result.is_refused ? (
                      <div style={{ background: '#FFF8E1', border: '1px solid #F9A825', borderLeft: '4px solid #F9A825', padding: '16px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#F57F17', marginBottom: '8px', fontFamily: 'sans-serif' }}>
                          âš  INSUFFICIENT CONTEXT
                        </div>
                        <div style={{ fontSize: '13px', color: '#555', fontFamily: 'sans-serif' }}>
                          {result.answer}
                        </div>
                      </div>
                    ) : (
                      <>
                        {/* Answer text */}
                        <div style={{
                          fontSize: '14px', lineHeight: '1.8', color: '#1a1a1a',
                          fontFamily: 'Georgia, serif', whiteSpace: 'pre-wrap',
                          borderBottom: '1px solid #E8EDF2', paddingBottom: '20px', marginBottom: '20px'
                        }}>
                          {result.answer}
                        </div>

                        {/* Citations Table */}
                        {result.citations.length > 0 && (
                          <div>
                            <div style={{
                              fontSize: '11px', fontWeight: 'bold', color: '#0A3055',
                              letterSpacing: '1px', marginBottom: '10px', fontFamily: 'sans-serif',
                              borderBottom: '2px solid #0A3055', paddingBottom: '6px'
                            }}>
                              LEGAL CITATIONS &amp; REFERENCES
                            </div>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: 'sans-serif' }}>
                              <thead>
                                <tr style={{ background: '#0A3055', color: '#fff' }}>
                                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '40px' }}>#</th>
                                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px' }}>DOCUMENT</th>
                                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '80px' }}>TYPE</th>
                                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '60px' }}>PAGE</th>
                                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '100px' }}>SECTION</th>
                                </tr>
                              </thead>
                              <tbody>
                                {result.citations.map((c, i) => {
                                  const cfg = DOC_TYPE_CONFIG[c.doc_type] || DOC_TYPE_CONFIG['act']
                                  return (
                                    <tr key={i} style={{ background: i % 2 === 0 ? '#F8F9FA' : '#fff', borderBottom: '1px solid #E8EDF2' }}>
                                      <td style={{ padding: '8px 12px', color: '#888', fontSize: '11px' }}>{i + 1}</td>
                                      <td style={{ padding: '8px 12px', color: '#0A3055', fontWeight: 'bold' }}>{c.doc_title || c.cited_title || c.doc_id || 'â€”'}</td>
                                      <td style={{ padding: '8px 12px' }}>
                                        <span style={{
                                          fontSize: '10px', padding: '2px 6px', fontWeight: 'bold',
                                          color: cfg.color, background: cfg.bg,
                                          border: `1px solid ${cfg.border}`, borderRadius: '2px'
                                        }}>
                                          {cfg.label}
                                        </span>
                                      </td>
                                      <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: '11px', color: '#333' }}>p.{c.page_number}</td>
                                      <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: '11px', color: '#1565C0' }}>{c.section_ref || 'â€”'}</td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {/* Sources Tab */}
                {activeTab === 'sources' && (
                  <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: 'none' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: 'sans-serif' }}>
                      <thead>
                        <tr style={{ background: '#0A3055', color: '#fff' }}>
                          <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '40px' }}>RANK</th>
                          <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px' }}>DOCUMENT</th>
                          <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '80px' }}>TYPE</th>
                          <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '55px' }}>PAGE</th>
                          <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', letterSpacing: '0.5px', width: '70px' }}>SCORE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.top_chunks.map((chunk, i) => {
                          const cfg = DOC_TYPE_CONFIG[chunk.doc_type] || DOC_TYPE_CONFIG['act']
                          return (
                            <tr key={i} style={{ borderBottom: '1px solid #E8EDF2', background: i % 2 === 0 ? '#F8F9FA' : '#fff' }}>
                              <td style={{ padding: '10px 12px', textAlign: 'center', fontFamily: 'monospace', fontSize: '11px', color: '#888' }}>#{i + 1}</td>
                              <td style={{ padding: '10px 12px' }}>
                                <div style={{ fontWeight: 'bold', color: '#0A3055', marginBottom: '4px' }}>{chunk.doc_title}</div>
                                <div style={{ fontSize: '11px', color: '#555', lineHeight: '1.5' }}>{chunk.text.slice(0, 180)}...</div>
                              </td>
                              <td style={{ padding: '10px 12px' }}>
                                <span style={{
                                  fontSize: '10px', padding: '2px 6px', fontWeight: 'bold',
                                  color: cfg.color, background: cfg.bg,
                                  border: `1px solid ${cfg.border}`, borderRadius: '2px'
                                }}>
                                  {cfg.label}
                                </span>
                              </td>
                              <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: '11px', color: '#333' }}>p.{chunk.page_number}</td>
                              <td style={{ padding: '10px 12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                  <div style={{
                                    height: '6px', width: `${Math.round(chunk.rerank_score * 60)}px`,
                                    background: chunk.rerank_score > 0.7 ? '#1B5E20' : chunk.rerank_score > 0.4 ? '#E65100' : '#888',
                                    borderRadius: '2px', minWidth: '4px'
                                  }} />
                                  <span style={{ fontSize: '10px', fontFamily: 'monospace', color: '#555' }}>
                                    {(chunk.rerank_score * 100).toFixed(0)}%
                                  </span>
                                </div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Empty state */}
            {!result && !loading && !error && (
              <div style={{ background: '#fff', border: '1px solid #CBD5E0', borderTop: '3px solid #0A3055', padding: '48px', textAlign: 'center' }}>
                <div style={{ fontSize: '48px', marginBottom: '16px' }}>âš–</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#0A3055', marginBottom: '8px' }}>
                  US Tax Law Research System
                </div>
                <div style={{ fontSize: '13px', color: '#555', maxWidth: '500px', margin: '0 auto', lineHeight: '1.8', fontFamily: 'sans-serif' }}>
                  Enter a legal question to search across <strong>101 authoritative documents</strong> including
                  IRC statutes, landmark court judgments, congressional analysis, and IRS publications.
                  Every answer includes precise citations with page numbers.
                </div>
                <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'center', gap: '16px', flexWrap: 'wrap' }}>
                  {[
                    { label: '30 IRC Statutes', color: '#1565C0', bg: '#E3F2FD' },
                    { label: '30 Court Cases', color: '#4A148C', bg: '#F3E5F5' },
                    { label: '30 CRS/GAO Reports', color: '#1B5E20', bg: '#E8F5E9' },
                    { label: '10 IRS Publications', color: '#E65100', bg: '#FFF3E0' },
                  ].map((item, i) => (
                    <span key={i} style={{
                      padding: '6px 14px', fontSize: '12px', fontWeight: 'bold',
                      color: item.color, background: item.bg,
                      border: `1px solid ${item.color}`, borderRadius: '2px',
                      fontFamily: 'sans-serif'
                    }}>
                      {item.label}
                    </span>
                  ))}
                </div>
              </div>
            )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* FOOTER */}
      <footer style={{ background: '#0D2137', color: '#888', padding: '20px 0', marginTop: '40px' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontFamily: 'sans-serif', fontSize: '11px' }}>
          <div>
            Legal RAG System &nbsp;Â·&nbsp; US Tax Law Research &nbsp;Â·&nbsp; Built with Elasticsearch + Groq
          </div>
        </div>
      </footer>

      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
          40% { transform: scale(1.0); opacity: 1; }
        }
        textarea:focus { border-color: #0A3055 !important; box-shadow: 0 0 0 2px rgba(10,48,85,0.2); }
        tr:hover td { background: #EBF5FB !important; }
      `}</style>
    </div>
  )
}
