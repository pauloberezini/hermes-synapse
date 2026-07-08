import type { Language } from '../i18n';
import { styles } from '../styles';

interface SettingsTabProps {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
}

export function SettingsTab({ language, setLanguage, t }: SettingsTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>{t('settingsTitle')}</h2>
          <p style={styles.tabSubtitle}>{t('settingsSubtitle')}</p>
        </div>
      </div>

      <div className="glass-panel" style={{ ...styles.configForm, maxWidth: 720 }}>
        <div style={styles.formGroup}>
          <label style={styles.formLabel}>{t('language')}</label>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {([
              ['ru', 'Русский'],
              ['en', 'English'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setLanguage(value)}
                className="btn-primary"
                style={{
                  borderColor: language === value ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.14)',
                  background: language === value ? 'rgba(0,240,255,0.12)' : 'rgba(255,255,255,0.03)',
                  color: language === value ? 'var(--accent-cyan)' : 'var(--text-muted)',
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <p style={styles.formHelp}>{t('languageHelp')}</p>
        </div>

        <div style={{
          padding: 14,
          borderRadius: 8,
          border: '1px solid rgba(16,185,129,0.22)',
          background: 'rgba(16,185,129,0.06)',
          color: 'var(--success)',
          fontSize: '0.9rem',
          fontWeight: 600,
        }}>
          {t('saveStatus')}
        </div>
      </div>
    </div>
  );
}
