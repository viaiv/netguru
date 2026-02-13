/**
 * CodeBlock — Syntax-highlighted code block with copy button.
 */
import { useState, useMemo } from 'react';
import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import yaml from 'highlight.js/lib/languages/yaml';
import json from 'highlight.js/lib/languages/json';
import python from 'highlight.js/lib/languages/python';
import xml from 'highlight.js/lib/languages/xml';
import plaintext from 'highlight.js/lib/languages/plaintext';
import routeros from 'highlight.js/lib/languages/routeros';

// Registrar linguagens usadas
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('yml', yaml);
hljs.registerLanguage('json', json);
hljs.registerLanguage('python', python);
hljs.registerLanguage('py', python);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('plaintext', plaintext);
hljs.registerLanguage('text', plaintext);
hljs.registerLanguage('routeros', routeros);
hljs.registerLanguage('cisco', routeros);

interface CodeBlockProps {
  code: string;
  language?: string;
}

function CodeBlock({ code, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const highlighted = useMemo(() => {
    const lang = language?.toLowerCase();
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  }, [code, language]);

  const displayLang = language || 'code';

  function handleCopy(): void {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span>{displayLang}</span>
        <button
          type="button"
          className={`code-block-copy ${copied ? 'code-block-copy--copied' : ''}`}
          onClick={handleCopy}
        >
          {copied ? 'Copiado!' : 'Copiar'}
        </button>
      </div>
      <div className="code-block-body">
        <code dangerouslySetInnerHTML={{ __html: highlighted }} />
      </div>
    </div>
  );
}

export default CodeBlock;
