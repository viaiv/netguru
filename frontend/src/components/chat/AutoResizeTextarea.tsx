/**
 * AutoResizeTextarea — Textarea that grows with content up to maxRows.
 */
import { useRef, useLayoutEffect, type TextareaHTMLAttributes } from 'react';

interface AutoResizeTextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  maxRows?: number;
}

function AutoResizeTextarea({ maxRows = 8, className, onChange, value, ...rest }: AutoResizeTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Reset height to get accurate scrollHeight
    el.style.height = 'auto';

    // Compute max height from maxRows
    const style = getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight) || 20;
    const paddingY = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const borderY = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    const maxHeight = lineHeight * maxRows + paddingY + borderY;

    const newHeight = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${newHeight}px`;
  }, [value, maxRows]);

  return (
    <textarea
      ref={ref}
      className={`chat-textarea chat-textarea--auto ${className ?? ''}`}
      value={value}
      onChange={onChange}
      rows={1}
      {...rest}
    />
  );
}

export default AutoResizeTextarea;
