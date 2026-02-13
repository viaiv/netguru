import { formatFileSize } from '../../services/fileApi';

// ---------------------------------------------------------------------------
//  Props
// ---------------------------------------------------------------------------

interface FileAttachmentChipProps {
  file: File;
  uploadProgress: number | null;
  uploadError: string | null;
  onRemove: () => void;
}

// ---------------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------------

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  if (['pcap', 'pcapng', 'cap'].includes(ext)) return '\uD83D\uDCE6'; // package
  if (['conf', 'cfg'].includes(ext)) return '\u2699\uFE0F';            // gear
  if (ext === 'log') return '\uD83D\uDCCB';                            // clipboard
  if (ext === 'pdf') return '\uD83D\uDCC4';                            // page
  return '\uD83D\uDCC2';                                               // folder
}

// ---------------------------------------------------------------------------
//  Component
// ---------------------------------------------------------------------------

function FileAttachmentChip({ file, uploadProgress, uploadError, onRemove }: FileAttachmentChipProps) {
  const isUploading = uploadProgress !== null && uploadProgress < 100;
  const hasError = uploadError !== null;

  return (
    <div className={`file-chip ${hasError ? 'file-chip--error' : ''}`}>
      <span className="file-chip__icon">{fileIcon(file.name)}</span>

      <div className="file-chip__info">
        <span className="file-chip__name" title={file.name}>
          {file.name}
        </span>
        <span className="file-chip__size">{formatFileSize(file.size)}</span>
      </div>

      <button
        type="button"
        className="file-chip__remove"
        onClick={onRemove}
        disabled={isUploading}
        aria-label="Remover arquivo"
      >
        &times;
      </button>

      {/* Progress bar */}
      {uploadProgress !== null && !hasError && (
        <div className="file-chip__progress" style={{ width: `${uploadProgress}%` }} />
      )}

      {/* Error message */}
      {hasError && <span className="file-chip__error">{uploadError}</span>}
    </div>
  );
}

export default FileAttachmentChip;
