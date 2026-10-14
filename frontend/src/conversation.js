// The single place that turns chat bubbles into the transcript the router scores
// and the model answers.
//
// The dashboard and its live route preview both call this, so a preview can never
// describe a different transcript than the one that would actually be sent. That
// was the bug that once put the current question in twice: two callers each
// assembled the conversation and only one of them was right.

export function buildConversation(base, query) {
  const history = (base || []).flatMap((m) =>
    m.role === 'user'
      ? [{ role: 'user', content: m.text }]
      : m.result?.response
        ? [{ role: 'assistant', content: m.result.response }]
        : []
  )
  return query == null ? history : [...history, { role: 'user', content: query }]
}
