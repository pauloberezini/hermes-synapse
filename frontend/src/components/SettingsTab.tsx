import { styles } from '../styles';

interface SettingsTabProps {
  t: (key: string) => string;
}

export function SettingsTab({ t }: SettingsTabProps) {
  return (
    <div style={styles.tabWrapper}>
      <div style={styles.tabHeader}>
        <div>
          <h2 className="glow-text-cyan" style={styles.tabTitle}>{t('settingsTitle')}</h2>
          <p style={styles.tabSubtitle}>{t('settingsSubtitle')}</p>
        </div>
      </div>

      <div className="glass-panel" style={{ ...styles.configForm, maxWidth: 720 }}>
        <div style={{
          padding: 14,
          borderRadius: 8,
          border: '1px solid rgba(115,217,255,0.2)',
          background: 'rgba(115,217,255,0.06)',
          color: 'var(--text-muted)',
          fontSize: '0.9rem',
          lineHeight: 1.5,
        }}>
          {t('generalSettingsHelp')}
        </div>
      </div>
    </div>
  );
}
