
export const styles: Record<string, any> = {
  sidebar: {
    width: '320px',
    height: '100%',
    padding: '24px',
    display: 'flex',
    flexDirection: 'column' as const,
    borderRight: 'var(--glass-border)',
    borderRadius: '0px 16px 16px 0px',
    backgroundColor: 'rgba(6, 9, 19, 0.85)',
    zIndex: 10
  },
  logoArea: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '4px'
  },
  logoTitle: {
    fontSize: '1.6rem',
    fontWeight: 700,
    letterSpacing: '3px'
  },
  logoSubtitle: {
    fontSize: '0.65rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)',
    letterSpacing: '1px',
    marginBottom: '32px',
    paddingLeft: '26px'
  },
  navMenu: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    flex: 1
  },
  navBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px 16px',
    borderRadius: '8px',
    background: 'transparent',
    border: '1px solid transparent',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-sans)',
    fontWeight: 500,
    fontSize: '0.95rem',
    cursor: 'pointer',
    textAlign: 'left' as const,
    transition: 'all 0.2s ease-in-out'
  },
  navBtnActive: {
    background: 'rgba(0, 240, 255, 0.08)',
    border: '1px solid rgba(0, 240, 255, 0.25)',
    color: 'var(--accent-cyan)',
    boxShadow: '0 0 15px rgba(0, 240, 255, 0.05)'
  },
  statusBox: {
    marginTop: 'auto',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    fontSize: '0.9rem',
    backgroundColor: 'rgba(8, 10, 15, 0.4)'
  },
  statusRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  statusLabel: {
    color: 'var(--text-muted)'
  },
  modelTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 8px',
    borderRadius: '6px',
    backgroundColor: 'rgba(0, 240, 255, 0.05)',
    border: '1px solid rgba(0, 240, 255, 0.15)'
  },
  modelName: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.75rem',
    color: 'var(--accent-cyan)',
    maxWidth: '120px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const
  },
  mainContent: {
    flex: 1,
    height: '100%',
    padding: '32px',
    overflowY: 'auto' as const
  },
  tabWrapper: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100%',
    gap: '24px'
  },
  tabHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  tabTitle: {
    fontSize: '1.4rem',
    fontWeight: 600,
    letterSpacing: '1px',
    marginBottom: '4px'
  },
  tabSubtitle: {
    fontSize: '0.85rem',
    color: 'var(--text-muted)'
  },
  chatArea: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    height: 'calc(100vh - 160px)',
    overflow: 'hidden',
    padding: '20px',
    backgroundColor: 'rgba(12, 17, 34, 0.5)'
  },
  chatScroller: {
    flex: 1,
    overflowY: 'auto' as const,
    paddingRight: '10px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '16px',
    marginBottom: '20px'
  },
  msgBubbleWrapper: {
    display: 'flex',
    width: '100%'
  },
  msgBubble: {
    maxWidth: '75%',
    padding: '14px 18px',
    borderRadius: '12px',
    border: '1px solid',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
  },
  msgHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '8px',
    fontSize: '0.75rem',
    fontWeight: 600,
    letterSpacing: '0.5px'
  },
  userLabel: {
    color: 'var(--accent-orange)'
  },
  assistantLabel: {
    color: 'var(--accent-cyan)'
  },
  chatIdLabel: {
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)'
  },
  msgText: {
    fontSize: '0.95rem',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
    color: 'var(--text-primary)'
  },
  systemMsg: {
    fontSize: '0.8rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)',
    padding: '4px 12px',
    borderRadius: '6px',
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    border: '1px solid rgba(255, 255, 255, 0.05)'
  },
  chatInputRow: {
    display: 'flex',
    gap: '12px',
    width: '100%'
  },
  chatInput: {
    flex: 1,
    minHeight: '44px',
    maxHeight: '160px',
    resize: 'none' as const,
    overflowY: 'auto' as const,
    lineHeight: '1.5',
    paddingTop: '11px',
    paddingBottom: '11px',
  },
  configForm: {
    padding: '32px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '24px',
    maxWidth: '800px',
    backgroundColor: 'rgba(12, 17, 34, 0.5)'
  },
  formGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px'
  },
  formLabel: {
    fontSize: '0.95rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  },
  formSelect: {
    width: '100%',
    height: '44px',
    backgroundColor: 'var(--bg-deep)'
  },
  formTextarea: {
    width: '100%',
    fontFamily: 'var(--font-sans)',
    lineHeight: 1.5,
    resize: 'vertical' as const
  },
  formHelp: {
    fontSize: '0.8rem',
    color: 'var(--text-muted)'
  },
  logsLayout: {
    display: 'grid',
    gridTemplateColumns: '350px 1fr',
    gap: '24px',
    height: 'calc(100vh - 160px)',
    overflow: 'hidden'
  },
  logsListWrapper: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100%',
    overflow: 'hidden',
    backgroundColor: 'rgba(12, 17, 34, 0.5)'
  },
  logsListHeader: {
    padding: '16px',
    borderBottom: 'var(--glass-border)',
    fontSize: '0.9rem',
    fontWeight: 600,
    color: 'var(--text-muted)'
  },
  logsList: {
    flex: 1,
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    padding: '12px',
    gap: '12px'
  },
  emptyLogs: {
    fontSize: '0.85rem',
    color: 'var(--text-muted)',
    textAlign: 'center' as const,
    marginTop: '32px',
    lineHeight: 1.5
  },
  logCard: {
    padding: '12px',
    borderRadius: '8px',
    border: '1px solid',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px'
  },
  logCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  logTime: {
    fontSize: '0.75rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)'
  },
  statusSuccess: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.7rem',
    color: '#10b981',
    fontWeight: 600
  },
  statusError: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.7rem',
    color: '#ef4444',
    fontWeight: 600
  },
  logCardQuery: {
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    fontWeight: 500
  },
  logCardStats: {
    display: 'flex',
    gap: '12px',
    fontSize: '0.75rem',
    color: 'var(--text-dim)'
  },
  statItem: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px'
  },
  logDetailWrapper: {
    height: '100%',
    overflowY: 'auto' as const,
    backgroundColor: 'rgba(12, 17, 34, 0.5)',
    padding: '24px'
  },
  logDetail: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '24px'
  },
  detailHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottom: 'var(--glass-border)',
    paddingBottom: '16px'
  },
  detailTitle: {
    fontSize: '1.1rem',
    fontWeight: 600,
    letterSpacing: '1px',
    color: 'var(--accent-cyan)'
  },
  detailTime: {
    fontSize: '0.8rem',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)'
  },
  detailGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '16px'
  },
  detailStatBox: {
    padding: '12px 16px',
    borderRadius: '8px',
    backgroundColor: 'rgba(6, 9, 19, 0.4)',
    border: 'var(--glass-border)',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '4px'
  },
  detailStatLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-dim)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px'
  },
  detailStatValue: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    wordBreak: 'break-all' as const
  },
  detailBlock: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '10px'
  },
  detailBlockTitle: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px'
  },
  codeBlock: {
    padding: '16px',
    borderRadius: '8px',
    backgroundColor: 'rgba(6, 9, 19, 0.6)',
    border: 'var(--glass-border)',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.85rem',
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const
  },
  emptyDetail: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column' as const,
    justifyContent: 'center',
    alignItems: 'center',
    color: 'var(--text-muted)',
    fontSize: '0.9rem',
    textAlign: 'center' as const,
    padding: '32px',
    lineHeight: 1.6
  },
  toolsLayout: {
    display: 'grid',
    gridTemplateColumns: '340px 1fr',
    gap: '24px',
    height: 'calc(100vh - 160px)',
    overflow: 'hidden'
  },
  toolsMetricsWrapper: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100%',
    padding: '24px',
    backgroundColor: 'rgba(12, 17, 34, 0.5)'
  },
  toolsPanelTitle: {
    fontSize: '1.1rem',
    fontWeight: 600,
    color: 'var(--accent-cyan)',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '20px',
    borderBottom: 'var(--glass-border)',
    paddingBottom: '12px'
  },
  metricsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '20px'
  },
  metricItem: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px'
  },
  metricLabelRow: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-primary)'
  },
  progressBarBg: {
    height: '10px',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: '5px',
    overflow: 'hidden',
    border: '1px solid rgba(255, 255, 255, 0.03)'
  },
  progressBarFill: {
    height: '100%',
    borderRadius: '5px',
    transition: 'width 0.5s ease-in-out'
  },
  metricHelpText: {
    fontSize: '0.75rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)'
  },
  telemetryStatusRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTop: 'var(--glass-border)',
    paddingTop: '20px',
    marginTop: '10px',
    fontSize: '0.85rem'
  },
  loadingStats: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    gap: '12px'
  },
  toolsContentRight: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '24px',
    height: '100%',
    overflowY: 'auto' as const,
    paddingRight: '6px'
  },
  toolsTimersWrapper: {
    padding: '24px',
    backgroundColor: 'rgba(12, 17, 34, 0.5)'
  },
  timersList: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '16px'
  },
  emptyTimersMsg: {
    fontSize: '0.9rem',
    color: 'var(--text-muted)',
    gridColumn: '1 / -1',
    textAlign: 'center' as const,
    padding: '32px 0',
    lineHeight: 1.6
  },
  timerCard: {
    border: '1px solid',
    borderRadius: '10px',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
    transition: 'all 0.3s ease'
  },
  timerHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  timerLabel: {
    fontWeight: 600,
    fontSize: '0.95rem',
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: '160px'
  },
  timerStatusBadge: {
    fontSize: '0.7rem',
    fontWeight: 600,
    padding: '2px 6px',
    borderRadius: '4px',
    border: '1px solid'
  },
  timerBody: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  countdownBox: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'flex-start'
  },
  countdownVal: {
    fontSize: '1.8rem',
    fontWeight: 700,
    color: 'var(--accent-cyan)',
    fontFamily: 'var(--font-mono)',
    lineHeight: 1.1,
    textShadow: '0 0 10px rgba(0, 240, 255, 0.3)'
  },
  countdownUnit: {
    fontSize: '0.7rem',
    color: 'var(--text-dim)'
  },
  timerMeta: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'flex-end',
    fontSize: '0.75rem',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
    gap: '2px'
  },
  toolsRegistryWrapper: {
    padding: '24px',
    backgroundColor: 'rgba(12, 17, 34, 0.5)',
    marginBottom: '24px'
  },
  registeredToolsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '16px'
  },
  toolRegistryItem: {
    padding: '16px',
    borderRadius: '8px',
    backgroundColor: 'rgba(6, 9, 19, 0.4)',
    border: 'var(--glass-border)'
  },
  toolRegistryHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '8px'
  },
  toolRegistryName: {
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
    fontSize: '0.95rem',
    color: 'var(--accent-cyan)'
  },
  toolRegistryTag: {
    fontSize: '0.7rem',
    color: 'var(--text-dim)',
    textTransform: 'uppercase' as const,
    border: '1px solid rgba(255, 255, 255, 0.1)',
    padding: '2px 6px',
    borderRadius: '4px'
  },
  toolRegistryDesc: {
    fontSize: '0.85rem',
    color: 'var(--text-muted)',
    lineHeight: 1.5
  },
  traceTimeline: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    padding: '16px',
    backgroundColor: 'rgba(6, 9, 19, 0.4)',
    border: 'var(--glass-border)',
    borderRadius: '8px'
  },
  traceNode: {
    borderLeft: '2px solid rgba(0, 240, 255, 0.2)',
    paddingLeft: '14px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '4px',
    position: 'relative' as const
  },
  traceNodeHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  traceStatusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    display: 'inline-block'
  },
  traceAgentName: {
    fontWeight: 600,
    fontSize: '0.8rem',
    color: 'var(--accent-cyan)',
    fontFamily: 'var(--font-mono)'
  },
  traceActionLabel: {
    fontSize: '0.75rem',
    fontWeight: 500,
    color: 'var(--text-muted)'
  },
  traceMessage: {
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
    lineHeight: 1.4,
    whiteSpace: 'pre-wrap' as const
  },
  traceTime: {
    fontSize: '0.75rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)'
  },
  datasetsWrapper: {
    display: 'flex',
    flexDirection: 'column' as const,
    padding: '24px',
    backgroundColor: 'rgba(12, 17, 34, 0.5)',
    borderRadius: '12px',
    border: 'var(--glass-border)'
  },
  datasetList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    marginTop: '12px',
    overflowY: 'auto' as const,
    maxHeight: '200px'
  },
  datasetItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '10px 12px',
    backgroundColor: 'rgba(6, 9, 19, 0.4)',
    border: 'var(--glass-border)',
    borderRadius: '6px'
  },
  datasetName: {
    fontSize: '0.85rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: '180px'
  },
  datasetSize: {
    fontSize: '0.75rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)'
  },
  uploadBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '44px',
    height: '44px',
    borderRadius: '8px',
    border: '1px solid rgba(0, 240, 255, 0.25)',
    backgroundColor: 'rgba(0, 240, 255, 0.05)',
    cursor: 'pointer',
    transition: 'all 0.2s ease'
  }
};
