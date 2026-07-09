
export const styles: Record<string, any> = {
  sidebar: {
    position: 'relative' as const,
    width: '320px',
    height: '100%',
    padding: '18px 20px 14px',
    display: 'flex',
    flexDirection: 'column' as const,
    overflow: 'hidden',
    borderRight: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '0px',
    background: 'linear-gradient(180deg, rgba(26, 22, 46, 0.9), rgba(12, 13, 23, 0.78))',
    boxShadow: '18px 0 70px rgba(0, 0, 0, 0.22), inset -1px 0 0 rgba(255, 255, 255, 0.03)',
    zIndex: 10
  },
  sidebarCollapsed: {
    width: '92px',
    padding: '18px 14px 14px',
    alignItems: 'center'
  },
  sidebarToggle: {
    position: 'absolute' as const,
    top: '18px',
    right: '-16px',
    zIndex: 20,
    width: '32px',
    height: '32px',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.12)',
    background: 'rgba(24, 23, 38, 0.92)',
    color: 'var(--text-muted)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.28)'
  },
  logoArea: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    marginBottom: '4px',
    flexShrink: 0
  },
  logoTitle: {
    fontSize: '1.42rem',
    fontWeight: 700,
    letterSpacing: '0px',
    lineHeight: 1
  },
  logoSubtitle: {
    fontSize: '0.62rem',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)',
    letterSpacing: '3px',
    textTransform: 'uppercase' as const,
    marginBottom: '18px',
    paddingLeft: '60px'
  },
  navMenu: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '7px',
    flex: '1 1 auto',
    minHeight: 0,
    overflowY: 'auto' as const,
    overflowX: 'hidden' as const,
    paddingRight: '2px',
    marginRight: '-2px'
  },
  navMenuCollapsed: {
    width: '100%',
    alignItems: 'center',
    paddingRight: 0,
    marginRight: 0
  },
  navBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    minHeight: '42px',
    padding: '9px 14px',
    borderRadius: '8px',
    background: 'rgba(255, 255, 255, 0.018)',
    border: '1px solid transparent',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-sans)',
    fontWeight: 600,
    fontSize: '0.78rem',
    cursor: 'pointer',
    textAlign: 'left' as const,
    transition: 'all 0.2s ease-in-out',
    letterSpacing: '1.7px',
    textTransform: 'uppercase' as const
  },
  navBtnActive: {
    background: '#f7f4ff',
    border: '1px solid rgba(255, 255, 255, 0.85)',
    color: '#11121c',
    boxShadow: '0 14px 34px rgba(155, 136, 255, 0.24)'
  },
  navBtnCollapsed: {
    width: '48px',
    height: '40px',
    minHeight: '40px',
    justifyContent: 'center',
    padding: '0',
    gap: '0'
  },
  statusBox: {
    marginTop: '10px',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '9px',
    fontSize: '0.82rem',
    background: 'rgba(255, 255, 255, 0.035)',
    flexShrink: 0,
    maxWidth: '100%'
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
    backgroundColor: 'rgba(155, 136, 255, 0.1)',
    border: '1px solid rgba(155, 136, 255, 0.24)'
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
    padding: '34px',
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
    fontSize: '1.55rem',
    fontWeight: 700,
    letterSpacing: '0px',
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
    background: 'rgba(18, 19, 32, 0.58)'
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
    borderRadius: '8px',
    border: '1px solid',
    boxShadow: '0 12px 30px rgba(0, 0, 0, 0.18)'
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
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    border: '1px solid rgba(255, 255, 255, 0.08)'
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
    background: 'rgba(18, 19, 32, 0.58)'
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
    background: 'rgba(18, 19, 32, 0.58)'
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
    background: 'rgba(18, 19, 32, 0.58)',
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
    backgroundColor: 'rgba(10, 11, 19, 0.46)',
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
    backgroundColor: 'rgba(10, 11, 19, 0.62)',
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
    background: 'rgba(18, 19, 32, 0.58)'
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
    backgroundColor: 'rgba(255, 255, 255, 0.07)',
    borderRadius: '5px',
    overflow: 'hidden',
    border: '1px solid rgba(255, 255, 255, 0.05)'
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
    background: 'rgba(18, 19, 32, 0.58)'
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
    borderRadius: '8px',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
    boxShadow: '0 12px 30px rgba(0, 0, 0, 0.18)',
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
    textShadow: '0 0 12px rgba(115, 217, 255, 0.32)'
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
    background: 'rgba(18, 19, 32, 0.58)',
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
    backgroundColor: 'rgba(10, 11, 19, 0.46)',
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
    borderLeft: '2px solid rgba(155, 136, 255, 0.24)',
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
  sceneShell: {
    position: 'relative' as const,
    height: 'min(680px, calc(100vh - 190px))',
    minHeight: '480px',
    overflow: 'hidden',
    borderRadius: '8px',
    border: 'var(--glass-border)',
    background: 'radial-gradient(circle at 50% 18%, rgba(155, 136, 255, 0.16), transparent 34%), rgba(8, 9, 16, 0.58)',
    boxShadow: 'var(--glass-shadow)'
  },
  sceneHeader: {
    position: 'absolute' as const,
    top: '22px',
    left: '24px',
    right: '24px',
    zIndex: 2,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    pointerEvents: 'none' as const
  },
  sceneKicker: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem',
    letterSpacing: '3px',
    color: 'var(--accent-cyan)',
    marginBottom: '8px'
  },
  sceneTitle: {
    fontSize: '2.5rem',
    lineHeight: 1,
    letterSpacing: '0px',
    margin: 0
  },
  sceneStats: {
    display: 'flex',
    gap: '10px',
    flexWrap: 'wrap' as const,
    justifyContent: 'flex-end'
  },
  sceneStat: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem',
    letterSpacing: '1.8px',
    padding: '9px 12px',
    borderRadius: '999px',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    background: 'rgba(20, 20, 33, 0.6)',
    backdropFilter: 'blur(14px)'
  },
  sceneCanvas: {
    position: 'absolute' as const,
    inset: 0,
    width: '100%',
    height: '100%',
    zIndex: 1
  },
  sceneLegend: {
    position: 'absolute' as const,
    left: '24px',
    bottom: '24px',
    zIndex: 2,
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap' as const,
    padding: '10px 12px',
    borderRadius: '999px',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    background: 'rgba(20, 20, 33, 0.58)',
    backdropFilter: 'blur(14px)'
  },
  sceneLegendItem: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '7px',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem',
    color: 'var(--text-muted)',
    textTransform: 'uppercase' as const,
    letterSpacing: '1px'
  },
  sceneLegendDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    display: 'inline-block'
  },
  sceneInspector: {
    position: 'absolute' as const,
    right: '24px',
    bottom: '24px',
    zIndex: 2,
    width: '320px',
    padding: '18px',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    background: 'linear-gradient(145deg, rgba(28, 27, 45, 0.82), rgba(13, 14, 24, 0.76))',
    boxShadow: '0 20px 55px rgba(0, 0, 0, 0.34)',
    backdropFilter: 'blur(18px)',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '14px'
  },
  sceneError: {
    position: 'absolute' as const,
    inset: '82px 24px 24px',
    zIndex: 3,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '8px',
    border: '1px solid rgba(255, 93, 143, 0.28)',
    background: 'rgba(20, 20, 33, 0.72)',
    color: 'var(--danger)',
    textAlign: 'center' as const,
    padding: '24px',
    lineHeight: 1.5
  },
  sceneInspectorHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    paddingBottom: '12px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)'
  },
  sceneInspectorTitle: {
    margin: 0,
    color: 'var(--text-primary)',
    fontSize: '1rem',
    fontWeight: 700
  },
  sceneInspectorMeta: {
    margin: '3px 0 0',
    color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.72rem'
  },
  sceneMetricGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '10px'
  },
  sceneMetric: {
    minWidth: 0,
    padding: '10px',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    background: 'rgba(255, 255, 255, 0.035)',
    color: 'var(--text-muted)',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
    fontSize: '0.73rem'
  },
  sceneInfoBlock: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '5px',
    color: 'var(--text-muted)',
    fontSize: '0.76rem'
  },
  sceneProgressTrack: {
    height: '4px',
    borderRadius: '999px',
    overflow: 'hidden',
    background: 'rgba(255, 255, 255, 0.09)'
  },
  sceneProgressFill: {
    height: '100%',
    borderRadius: '999px',
    boxShadow: '0 0 12px currentColor'
  },
  sceneActionRow: {
    display: 'flex',
    gap: '10px',
    alignItems: 'center'
  },
  uploadBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '44px',
    height: '44px',
    borderRadius: '8px',
    border: '1px solid rgba(155, 136, 255, 0.28)',
    backgroundColor: 'rgba(155, 136, 255, 0.08)',
    cursor: 'pointer',
    transition: 'all 0.2s ease'
  }
};
