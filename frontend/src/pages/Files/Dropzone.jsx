import { CloudUpload } from 'lucide-react'
import { useRef, useState } from 'react'
import { cn } from '../../utils/cn'
import styles from './Dropzone.module.css'

/** Drag & drop target that is also a keyboard-accessible "browse" button. */
export function Dropzone({ onFiles, disabled = false, multiple = true, accept }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const depth = useRef(0) // dragenter/leave fire for children too

  const emit = (fileList) => {
    if (!disabled && fileList?.length) onFiles(fileList)
  }

  return (
    <div
      className={cn(styles.dropzone, dragging && styles.dragging, disabled && styles.disabled)}
      onDragEnter={(e) => {
        e.preventDefault()
        depth.current += 1
        setDragging(true)
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1
        if (depth.current <= 0) setDragging(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        depth.current = 0
        setDragging(false)
        emit(e.dataTransfer.files)
      }}
    >
      <span className={styles.icon}>
        <CloudUpload size={22} aria-hidden="true" />
      </span>
      <p className={styles.title}>{dragging ? 'Drop to upload' : 'Drag & drop files here'}</p>
      <p className={styles.sub}>
        or{' '}
        <button type="button" className={styles.browse} onClick={() => inputRef.current?.click()} disabled={disabled}>
          browse your computer
        </button>
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple={multiple}
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          emit(e.target.files)
          e.target.value = '' // allow re-selecting the same file
        }}
      />
    </div>
  )
}
