import { cn } from '../../utils/cn'
import styles from './Card.module.css'

/**
 * Surface container. Compose with Card.Header / Card.Body / Card.Footer, or
 * pass `title` / `description` / `actions` for the common case.
 */
export function Card({ title, description, actions, icon: Icon, padded = true, className, children, as: Tag = 'section', ...props }) {
  return (
    <Tag className={cn(styles.card, className)} {...props}>
      {(title || actions) && (
        <CardHeader>
          <div className={styles.headingGroup}>
            {Icon && (
              <span className={styles.icon}>
                <Icon size={16} aria-hidden="true" />
              </span>
            )}
            <div>
              {title && <h2 className={styles.title}>{title}</h2>}
              {description && <p className={styles.description}>{description}</p>}
            </div>
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </CardHeader>
      )}
      {padded ? <div className={styles.body}>{children}</div> : children}
    </Tag>
  )
}

function CardHeader({ className, children }) {
  return <header className={cn(styles.header, className)}>{children}</header>
}

function CardBody({ className, children }) {
  return <div className={cn(styles.body, className)}>{children}</div>
}

function CardFooter({ className, children }) {
  return <footer className={cn(styles.footer, className)}>{children}</footer>
}

Card.Header = CardHeader
Card.Body = CardBody
Card.Footer = CardFooter
