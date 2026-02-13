/**
 * MarkdownContent — Renderiza markdown nas mensagens do assistente.
 *
 * Usa react-markdown + remark-gfm. Code blocks fenced delegam para CodeBlock.
 * Durante streaming, detecta code fences incompletos e fecha temporariamente.
 */
import { memo, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

import CodeBlock from './CodeBlock';

interface MarkdownContentProps {
  content: string;
  isStreaming?: boolean;
}

/**
 * Durante streaming, se houver um numero impar de ``` (code fence aberto
 * sem fechar), fecha temporariamente para que o markdown renderize corretamente.
 */
function patchStreamingContent(raw: string): string {
  const fenceCount = (raw.match(/```/g) || []).length;
  if (fenceCount % 2 !== 0) {
    return raw + '\n```';
  }
  return raw;
}

const components: Components = {
  code({ className, children, ...props }) {
    // react-markdown coloca className="language-xxx" em fenced code blocks
    const match = /language-(\w+)/.exec(className || '');
    const isBlock = match || (typeof children === 'string' && children.includes('\n'));

    if (isBlock) {
      const lang = match?.[1];
      const code = String(children).replace(/\n$/, '');
      return <CodeBlock code={code} language={lang} />;
    }

    // Inline code
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },

  // Evitar <pre> wrapper duplicado — CodeBlock ja faz seu proprio container
  pre({ children }) {
    return <>{children}</>;
  },

  a({ href, children, ...props }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
};

function MarkdownContentInner({ content, isStreaming }: MarkdownContentProps) {
  const processed = useMemo(
    () => (isStreaming ? patchStreamingContent(content) : content),
    [content, isStreaming],
  );

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={components}>
        {processed}
      </ReactMarkdown>
    </div>
  );
}

// Memoizar mensagens ja completas (nao durante streaming)
const MarkdownContent = memo(MarkdownContentInner, (prev, next) => {
  if (next.isStreaming) return false; // sempre re-renderizar durante streaming
  return prev.content === next.content;
});

MarkdownContent.displayName = 'MarkdownContent';

export default MarkdownContent;
