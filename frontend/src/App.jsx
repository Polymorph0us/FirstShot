import { useState, useEffect, useRef } from 'react';
import {
  Shield,
  Clock,
  Target,
  CheckCircle2,
  XCircle,
  Play,
  Square,
  RefreshCw,
  Trash2,
  ExternalLink,
  Calendar,
  MapPin,
  Plus,
  User as UserIcon,
  LogOut,
  Monitor
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'targets' | 'activity' | 'settings'
  const [sessionStatus, setSessionStatus] = useState({ authenticated: false, message: 'Checking...' });
  const [targets, setTargets] = useState([]);
  const [attempts, setAttempts] = useState([]);
  const [events, setEvents] = useState([]);
  const [terms, setTerms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  // Authentication State
  const [currentUser, setCurrentUser] = useState(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'register'
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  // Remote Interactive Screencast Modal State
  const [showRemoteAuthModal, setShowRemoteAuthModal] = useState(false);
  const [remoteStatus, setRemoteStatus] = useState('Connecting to isolated remote browser...');
  const canvasRef = useRef(null);
  const remoteWsRef = useRef(null);

  // Filter for portal events
  const [filterDate, setFilterDate] = useState(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split('T')[0];
  });
  const [filterTerm, setFilterTerm] = useState('');

  // Modals
  const [armModalTarget, setArmModalTarget] = useState(null);
  const [armPurpose, setArmPurpose] = useState('Academic Continuous Assessment');
  const [armAcceptWaitlist, setArmAcceptWaitlist] = useState(false);
  const [armUserConsent, setArmUserConsent] = useState(false);
  const [armingLoading, setArmingLoading] = useState(false);

  const [preflightResult, setPreflightResult] = useState(null);
  const [preflightLoadingId, setPreflightLoadingId] = useState(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [manualTitle, setManualTitle] = useState('Module Assessment');
  const [manualDate, setManualDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  });
  const [manualRoom, setManualRoom] = useState('1731');
  const [manualStartTime, setManualStartTime] = useState('08:00');
  const [manualEndTime, setManualEndTime] = useState('09:29');

  const wsRef = useRef(null);

  const showToast = (message, type = 'info') => {
    setToast({ message, type, id: Date.now() });
    setTimeout(() => {
      setToast((cur) => (cur?.message === message ? null : cur));
    }, 5000);
  };

  const authFetch = async (url, options = {}) => {
    const token = localStorage.getItem('fs_token');
    const headers = { ...(options.headers || {}) };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(url, { ...options, credentials: 'include', headers });
    if (res.status === 401) {
      setCurrentUser(null);
      setShowAuthModal(true);
    }
    return res;
  };

  useEffect(() => {
    checkCurrentUser();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const checkCurrentUser = async () => {
    try {
      const res = await authFetch('/api/auth/me');
      if (res.ok) {
        const data = await res.json();
        setCurrentUser(data);
        setShowAuthModal(false);
        fetchSession();
        fetchTargets();
        fetchAttempts();
        fetchTerms();
        initWebSocket();
      } else {
        setCurrentUser(null);
        setShowAuthModal(true);
      }
    } catch {
      setCurrentUser(null);
      setShowAuthModal(true);
    }
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthError('');
    try {
      const endpoint = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username: authUsername.trim(), password: authPassword })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Authentication failed');
      localStorage.setItem('fs_token', data.token);
      setCurrentUser(data.user);
      setShowAuthModal(false);
      setAuthPassword('');
      showToast(authMode === 'login' ? `Welcome back, ${data.user.username}!` : `Account created for ${data.user.username}!`, 'success');
      fetchSession();
      fetchTargets();
      fetchAttempts();
      fetchTerms();
      initWebSocket();
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await authFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // Ignore
    }
    localStorage.removeItem('fs_token');
    setCurrentUser(null);
    setTargets([]);
    setAttempts([]);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setShowAuthModal(true);
    showToast('Logged out successfully.', 'info');
  };

  const fetchSession = async () => {
    try {
      const res = await authFetch('/api/session/status');
      const data = await res.json();
      setSessionStatus(data);
    } catch {
      setSessionStatus({ authenticated: false, message: 'Backend unreachable' });
    }
  };

  const fetchTargets = async () => {
    try {
      const res = await authFetch('/api/preferences/');
      const data = await res.json();
      if (Array.isArray(data)) setTargets(data);
    } catch (e) {
      console.error('Failed to load targets', e);
    }
  };

  const fetchAttempts = async () => {
    try {
      const res = await authFetch('/api/booking/attempts');
      const data = await res.json();
      if (Array.isArray(data)) setAttempts(data);
    } catch (e) {
      console.error('Failed to load attempts', e);
    }
  };

  const fetchTerms = async () => {
    try {
      const res = await authFetch('/api/events/terms');
      const data = await res.json();
      if (Array.isArray(data)) setTerms(data);
    } catch (e) {
      console.error('Failed to load terms', e);
    }
  };

  const fetchPortalEvents = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      if (filterDate) {
        query.append('date_from', filterDate);
        query.append('date_to', filterDate);
      }
      if (filterTerm) query.append('event_term', filterTerm);
      const res = await authFetch(`/api/events/?${query.toString()}`);
      const data = await res.json();
      if (Array.isArray(data)) setEvents(data);
    } catch {
      showToast('Error querying portal events', 'error');
    } finally {
      setLoading(false);
    }
  };

  const initWebSocket = () => {
    const token = localStorage.getItem('fs_token');
    if (!token) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'TARGET_STATUS_CHANGED') {
          showToast(`⚡ ${data.event_title}: ${data.old_status} → ${data.new_status}`, 'info');
          fetchTargets();
        } else if (data.type === 'AUTO_BOOKING_ATTEMPT') {
          showToast(`🚀 Attempt #${data.attempt_count}: ${data.event_title} (${data.room})`, 'warning');
          fetchAttempts();
        } else if (data.type === 'PORTAL_CRASH_RETRY') {
          showToast(`⚠️ Surge retry #${data.attempt_count}: ${data.error_message}`, 'warning');
          fetchAttempts();
        } else if (data.type === 'AUTO_BOOKING_SUCCESS') {
          showToast(`🎉 CONFIRMED: ${data.event_title} in Room ${data.room}!`, 'success');
          fetchTargets();
          fetchAttempts();
        } else if (data.type === 'AUTO_BOOKING_FAILED') {
          showToast(`❌ Booking failed: ${data.message}`, 'error');
          fetchTargets();
          fetchAttempts();
        } else if (data.type === 'TARGETS_UPDATED') {
          fetchTargets();
        }
      } catch (err) {
        console.error('WS parse error', err);
      }
    };

    ws.onclose = () => {
      if (localStorage.getItem('fs_token')) {
        setTimeout(initWebSocket, 4000);
      }
    };
  };

  // Remote Interactive Screencast WebSocket Connection
  useEffect(() => {
    if (!showRemoteAuthModal) {
      if (remoteWsRef.current) {
        remoteWsRef.current.close();
        remoteWsRef.current = null;
      }
      return;
    }

    const token = localStorage.getItem('fs_token');
    if (!token) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/session/remote-auth?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    remoteWsRef.current = ws;
    setRemoteStatus('Connecting to isolated remote browser...');

    ws.onopen = () => {
      setRemoteStatus('Browser active. Click and type below to log into your Saveetha account:');
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'frame' && canvasRef.current) {
          const canvas = canvasRef.current;
          const ctx = canvas.getContext('2d');
          const img = new Image();
          img.onload = () => {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          };
          img.src = 'data:image/jpeg;base64,' + msg.data;
        } else if (msg.type === 'authenticated') {
          showToast(msg.message, 'success');
          fetchSession();
          setTimeout(() => setShowRemoteAuthModal(false), 1500);
        } else if (msg.type === 'error') {
          setRemoteStatus(`Error: ${msg.message}`);
          showToast(msg.message, 'error');
        }
      } catch (err) {
        console.error('Remote auth message error', err);
      }
    };

    ws.onclose = () => {
      setRemoteStatus('Remote browser session ended.');
    };

    return () => {
      if (remoteWsRef.current) {
        remoteWsRef.current.close();
        remoteWsRef.current = null;
      }
    };
  }, [showRemoteAuthModal]);

  const sendRemoteMouseEvent = (action, e) => {
    if (!remoteWsRef.current || remoteWsRef.current.readyState !== WebSocket.OPEN) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    remoteWsRef.current.send(JSON.stringify({
      type: 'mouse',
      action,
      x,
      y,
      button: e.button === 2 ? 'right' : 'left',
      clickCount: 1
    }));
  };

  const sendRemoteKeyEvent = (action, e) => {
    if (!remoteWsRef.current || remoteWsRef.current.readyState !== WebSocket.OPEN) return;
    if (e.key === 'F12' || e.altKey) return;
    e.preventDefault();
    remoteWsRef.current.send(JSON.stringify({
      type: 'key',
      action,
      key: e.key,
      code: e.code,
      text: e.key.length === 1 ? e.key : undefined
    }));
  };

  const handleArmTarget = async () => {
    if (!armModalTarget) return;
    if (!armUserConsent) {
      showToast('You must authorize automated execution to arm target.', 'error');
      return;
    }
    setArmingLoading(true);
    try {
      const res = await authFetch(`/api/preferences/${armModalTarget.id}/arm`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          purpose: armPurpose,
          accept_waitlist: armAcceptWaitlist,
          user_permitted_automation: true,
          booking_mode: 'AUTO_BOOK'
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Arming failed');
      showToast(`Target armed: ${armModalTarget.event_title}`, 'success');
      setArmModalTarget(null);
      fetchTargets();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setArmingLoading(false);
    }
  };

  const handleDisarmTarget = async (id) => {
    try {
      const res = await authFetch(`/api/preferences/${id}/disarm`, { method: 'PUT' });
      if (!res.ok) throw new Error('Disarm failed');
      showToast('Target disarmed', 'info');
      fetchTargets();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleRunPreflight = async (id) => {
    setPreflightLoadingId(id);
    try {
      const res = await authFetch(`/api/preferences/${id}/preflight`, { method: 'POST' });
      const data = await res.json();
      setPreflightResult(data);
      fetchTargets();
    } catch {
      showToast('Preflight check failed to run', 'error');
    } finally {
      setPreflightLoadingId(null);
    }
  };

  const handleDeleteTarget = async (id) => {
    if (!confirm('Remove this target slot?')) return;
    try {
      const res = await authFetch(`/api/preferences/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      showToast('Target removed', 'info');
      fetchTargets();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleAddManualTarget = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch('/api/preferences/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_title: manualTitle,
          target_date: manualDate,
          preferred_room: manualRoom,
          preferred_start_time: manualStartTime,
          preferred_end_time: manualEndTime,
          accept_waitlist: false,
          monitoring_enabled: true
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Creation failed');
      showToast(`Target added: ${manualTitle} (Room ${manualRoom})`, 'success');
      setShowAddModal(false);
      fetchTargets();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleAddFromCard = async (evt) => {
    try {
      const res = await authFetch('/api/preferences/from-card', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: evt.event_id,
          title: evt.title,
          date: evt.date,
          start_time: evt.start_time,
          end_time: evt.end_time,
          venue: evt.venue,
          accept_waitlist: false,
          monitoring_enabled: true
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to select target');
      showToast(`Target saved: ${evt.title} (${evt.venue})`, 'success');
      fetchTargets();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleReauthenticate = async () => {
    try {
      showToast('Launching browser on workstation display...', 'info');
      const res = await authFetch('/api/session/reauthenticate', { method: 'POST' });
      const data = await res.json();
      showToast(data.message, data.success ? 'success' : 'warning');
      fetchSession();
    } catch {
      showToast('Failed to trigger reauthentication', 'error');
    }
  };

  // Determine Primary / Next Scheduled Target
  const primaryTarget = targets.find((t) => t.is_armed) || targets[0] || null;
  const armedCount = targets.filter((t) => t.is_armed).length;
  const confirmedCount = attempts.filter((a) => a.status === 'CONFIRMED').length;

  return (
    <div style={styles.container}>
      {/* Top Minimal Navigation */}
      <header style={styles.header}>
        <div style={styles.navLeft}>
          <div style={styles.logoBadge}>FS</div>
          <span style={styles.logoTitle}>FirstShot</span>
          <span style={styles.versionBadge}>v1.0</span>

          <nav style={styles.navLinks}>
            <button
              onClick={() => setActiveTab('overview')}
              style={{ ...styles.navButton, ...(activeTab === 'overview' ? styles.navButtonActive : {}) }}
            >
              Overview
            </button>
            <button
              onClick={() => setActiveTab('targets')}
              style={{ ...styles.navButton, ...(activeTab === 'targets' ? styles.navButtonActive : {}) }}
            >
              Targets
              {targets.length > 0 && <span style={styles.pillCount}>{targets.length}</span>}
            </button>
            <button
              onClick={() => setActiveTab('activity')}
              style={{ ...styles.navButton, ...(activeTab === 'activity' ? styles.navButtonActive : {}) }}
            >
              Activity
              {attempts.length > 0 && <span style={styles.pillCount}>{attempts.length}</span>}
            </button>
            <button
              onClick={() => setActiveTab('settings')}
              style={{ ...styles.navButton, ...(activeTab === 'settings' ? styles.navButtonActive : {}) }}
            >
              Settings
            </button>
          </nav>
        </div>

        <div style={styles.navRight}>
          <div
            onClick={() => {
              if (!sessionStatus.authenticated) setShowRemoteAuthModal(true);
            }}
            style={{ ...styles.sessionStatus, cursor: sessionStatus.authenticated ? 'default' : 'pointer' }}
            title={sessionStatus.authenticated ? 'Saveetha Portal Connected' : 'Click to launch interactive remote portal login'}
          >
            <span
              style={{
                ...styles.statusDot,
                backgroundColor: sessionStatus.authenticated ? '#10b981' : '#ef4444'
              }}
            />
            <span style={styles.statusLabel}>
              {sessionStatus.authenticated ? 'Saveetha Connected' : 'Portal Offline (Click to Connect)'}
            </span>
          </div>

          {currentUser ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#e5e7eb', background: '#1c1c1f', padding: '4px 10px', borderRadius: 6, border: '1px solid #27272a' }}>
                <UserIcon size={13} style={{ color: '#a1a1aa' }} />
                <span>{currentUser.username}</span>
                {currentUser.role === 'owner' ? (
                  <span style={{ color: '#38bdf8', fontSize: 11, background: '#0284c722', padding: '1px 5px', borderRadius: 4, border: '1px solid #0284c744' }}>Owner</span>
                ) : (
                  <span style={{ color: '#a1a1aa', fontSize: 11, background: '#27272a', padding: '1px 5px', borderRadius: 4 }}>Student</span>
                )}
              </div>
              <button
                onClick={handleLogout}
                style={{ background: 'transparent', border: '1px solid #27272a', color: '#a1a1aa', padding: '5px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
                title="Sign out of FirstShot"
              >
                <LogOut size={12} />
                Logout
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowAuthModal(true)}
              style={styles.primaryActionBtn}
            >
              <UserIcon size={13} style={{ marginRight: 6 }} />
              Sign In
            </button>
          )}
        </div>
      </header>

      {/* Main Container */}
      <main style={styles.mainContent}>
        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && (
          <div style={styles.tabSection}>
            {/* Hero / Next Target Banner */}
            <div style={styles.heroCard}>
              <div style={styles.heroHeader}>
                <span style={styles.heroLabel}>
                  {primaryTarget?.is_armed ? '⚡ Armed for Autonomous Execution' : 'Primary Target Slot'}
                </span>
                {primaryTarget && (
                  <span
                    style={{
                      ...styles.statusBadge,
                      ...getStatusBadgeStyle(primaryTarget.current_status)
                    }}
                  >
                    {primaryTarget.current_status || 'Checking Availability'}
                  </span>
                )}
              </div>

              {primaryTarget ? (
                <div style={styles.heroBody}>
                  <div style={styles.heroMainInfo}>
                    <h2 style={styles.heroTitle}>{primaryTarget.event_title}</h2>
                    <div style={styles.heroMetaRow}>
                      <span style={styles.heroMetaItem}>
                        <Calendar size={14} style={{ marginRight: 6 }} />
                        {primaryTarget.target_date || 'Target Date Pending'}
                      </span>
                      <span style={styles.heroMetaItem}>
                        <MapPin size={14} style={{ marginRight: 6 }} />
                        Room {primaryTarget.preferred_room}
                      </span>
                      <span style={styles.heroMetaItem}>
                        <Clock size={14} style={{ marginRight: 6 }} />
                        {primaryTarget.preferred_start_time}
                        {primaryTarget.preferred_end_time ? ` - ${primaryTarget.preferred_end_time}` : ''}
                      </span>
                    </div>
                  </div>

                  <div style={styles.heroActions}>
                    {primaryTarget.is_armed ? (
                      <button
                        onClick={() => handleDisarmTarget(primaryTarget.id)}
                        style={styles.heroDisarmBtn}
                      >
                        <Square size={14} style={{ marginRight: 6 }} />
                        Disarm
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setArmModalTarget(primaryTarget);
                          setArmPurpose(primaryTarget.purpose || 'Academic Continuous Assessment');
                          setArmAcceptWaitlist(primaryTarget.accept_waitlist || false);
                          setArmUserConsent(false);
                        }}
                        style={styles.heroArmBtn}
                      >
                        <Play size={14} style={{ marginRight: 6 }} />
                        Pre-Arm Auto-Book
                      </button>
                    )}
                    <button
                      onClick={() => handleRunPreflight(primaryTarget.id)}
                      disabled={preflightLoadingId === primaryTarget.id}
                      style={styles.heroSecondaryBtn}
                    >
                      <Shield size={14} style={{ marginRight: 6 }} />
                      Preflight Audit
                    </button>
                  </div>
                </div>
              ) : (
                <div style={styles.emptyHero}>
                  <Target size={24} style={{ color: '#6366f1', marginBottom: 8 }} />
                  <p style={{ color: '#999', fontSize: 13 }}>No target slots configured yet.</p>
                  <button onClick={() => setShowAddModal(true)} style={styles.addBtnSmall}>
                    <Plus size={14} style={{ marginRight: 4 }} />
                    Add First Target
                  </button>
                </div>
              )}
            </div>

            {/* Quick Metrics */}
            <div style={styles.metricsGrid}>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Configured Targets</span>
                <span style={styles.metricVal}>{targets.length}</span>
                <span style={styles.metricSub}>Monitored slots</span>
              </div>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Armed Targets</span>
                <span style={{ ...styles.metricVal, color: armedCount > 0 ? '#6366f1' : '#fff' }}>
                  {armedCount}
                </span>
                <span style={styles.metricSub}>Ready for 7:00 PM IST opening</span>
              </div>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Confirmed Bookings</span>
                <span style={{ ...styles.metricVal, color: '#10b981' }}>{confirmedCount}</span>
                <span style={styles.metricSub}>Verified with college server</span>
              </div>
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>Engine Cadence</span>
                <span style={styles.metricVal}>Adaptive</span>
                <span style={styles.metricSub}>60s idle · 5s near · 2s blitz</span>
              </div>
            </div>

            {/* Recent Live Activity */}
            <div style={styles.sectionHeader}>
              <h3 style={styles.sectionTitle}>Recent Booking Execution Log</h3>
              <button onClick={fetchAttempts} style={styles.refreshIconBtn} title="Refresh">
                <RefreshCw size={13} />
              </button>
            </div>

            <div style={styles.tableCard}>
              {attempts.length === 0 ? (
                <div style={styles.emptyTable}>No execution attempts logged yet.</div>
              ) : (
                <div style={styles.compactList}>
                  {attempts.slice(0, 5).map((att) => (
                    <div key={att.id} style={styles.compactRow}>
                      <div style={styles.compactColLeft}>
                        <div style={styles.compactTitle}>
                          {att.session_id ? `Session #${att.session_id}` : 'Autonomous Trigger'}
                        </div>
                        <div style={styles.compactSubtitle}>
                          {att.attempted_at ? new Date(att.attempted_at).toLocaleString() : 'Just now'} · Mode:{' '}
                          {att.mode} · Retries: {att.retry_count || 0}
                        </div>
                      </div>
                      <div style={styles.compactColRight}>
                        <span
                          style={{
                            ...styles.statusBadge,
                            ...getAttemptBadgeStyle(att.status)
                          }}
                        >
                          {att.status}
                        </span>
                        {att.execution_duration_ms && (
                          <span style={styles.durationPill}>{att.execution_duration_ms}ms</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TARGETS TAB */}
        {activeTab === 'targets' && (
          <div style={styles.tabSection}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h2 style={styles.pageTitle}>Target Assessment Slots</h2>
                <p style={styles.pageSubtitle}>
                  Targets configured for continuous monitoring and autonomous pre-armed booking.
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setShowAddModal(true)} style={styles.primaryActionBtn}>
                  <Plus size={14} style={{ marginRight: 6 }} />
                  Add Target
                </button>
              </div>
            </div>

            {/* Target List Card */}
            <div style={styles.tableCard}>
              {targets.length === 0 ? (
                <div style={styles.emptyTable}>No targets saved. Click "Add Target" to create one.</div>
              ) : (
                <div style={styles.compactList}>
                  {targets.map((tgt) => (
                    <div key={tgt.id} style={styles.targetRow}>
                      <div style={styles.targetInfoCol}>
                        <div style={styles.targetTitleRow}>
                          <span style={styles.targetName}>{tgt.event_title}</span>
                          <span
                            style={{
                              ...styles.statusBadge,
                              ...getStatusBadgeStyle(tgt.current_status)
                            }}
                          >
                            {tgt.current_status || 'Checking'}
                          </span>
                          <span
                            style={{
                              ...styles.modeBadge,
                              ...(tgt.booking_mode === 'AUTO_BOOK' ? styles.modeBadgeAuto : {})
                            }}
                          >
                            {tgt.booking_mode || 'OBSERVE'}
                          </span>
                          {tgt.is_armed && <span style={styles.armedPill}>ARMED</span>}
                        </div>

                        <div style={styles.targetMetaRow}>
                          <span>📅 {tgt.target_date || 'Any Date'}</span>
                          <span>🏢 Room {tgt.preferred_room || 'Any'}</span>
                          <span>
                            ⏰ {tgt.preferred_start_time} - {tgt.preferred_end_time || 'N/A'}
                          </span>
                          {tgt.capacity && <span>Capacity: {tgt.capacity}</span>}
                        </div>
                      </div>

                      <div style={styles.targetActionsCol}>
                        {tgt.is_armed ? (
                          <button
                            onClick={() => handleDisarmTarget(tgt.id)}
                            style={styles.actionBtnDisarm}
                            title="Disarm autonomous booking"
                          >
                            <Square size={13} style={{ marginRight: 4 }} />
                            Disarm
                          </button>
                        ) : (
                          <button
                            onClick={() => {
                              setArmModalTarget(tgt);
                              setArmPurpose(tgt.purpose || 'Academic Continuous Assessment');
                              setArmAcceptWaitlist(tgt.accept_waitlist || false);
                              setArmUserConsent(false);
                            }}
                            disabled={tgt.current_status === 'Booked'}
                            style={styles.actionBtnArm}
                            title="Pre-arm target for autonomous submission"
                          >
                            <Play size={13} style={{ marginRight: 4 }} />
                            Arm
                          </button>
                        )}

                        <button
                          onClick={() => handleRunPreflight(tgt.id)}
                          disabled={preflightLoadingId === tgt.id}
                          style={styles.actionBtnIcon}
                          title="Run 8-point preflight audit"
                        >
                          <Shield size={14} />
                        </button>

                        <button
                          onClick={() => handleDeleteTarget(tgt.id)}
                          style={styles.actionBtnDanger}
                          title="Remove target"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Portal Live Event Discovery Browser */}
            <div style={{ marginTop: 28 }}>
              <div style={styles.sectionHeaderRow}>
                <div>
                  <h3 style={styles.sectionTitle}>Browse Live Portal Sessions</h3>
                  <p style={styles.pageSubtitle}>
                    Inspect real sessions currently published on Saveetha learner portal.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="date"
                    value={filterDate}
                    onChange={(e) => setFilterDate(e.target.value)}
                    style={styles.dateInput}
                  />
                  <select
                    value={filterTerm}
                    onChange={(e) => setFilterTerm(e.target.value)}
                    style={styles.selectInput}
                  >
                    <option value="">All Terms</option>
                    {terms.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={fetchPortalEvents}
                    disabled={loading}
                    style={styles.primaryActionBtn}
                  >
                    <RefreshCw size={13} style={{ marginRight: 6 }} />
                    Query Portal
                  </button>
                </div>
              </div>

              <div style={styles.tableCard}>
                {loading ? (
                  <div style={styles.emptyTable}>Fetching live assessment cards from portal...</div>
                ) : events.length === 0 ? (
                  <div style={styles.emptyTable}>
                    No events retrieved yet. Choose a date and click "Query Portal".
                  </div>
                ) : (
                  <div style={styles.compactList}>
                    {events.map((evt) => (
                      <div key={evt.event_id} style={styles.portalCardRow}>
                        <div style={styles.portalCardLeft}>
                          <div style={styles.portalCardTitleRow}>
                            <span style={styles.portalCardTitle}>{evt.title}</span>
                            <span
                              style={{
                                ...styles.statusBadge,
                                ...getStatusBadgeStyle(evt.booking_status)
                              }}
                            >
                              {evt.booking_status}
                            </span>
                          </div>
                          <div style={styles.targetMetaRow}>
                            <span>📅 {evt.date}</span>
                            <span>🏢 Room {evt.venue}</span>
                            <span>
                              ⏰ {evt.start_time} - {evt.end_time}
                            </span>
                            {evt.capacity && <span>Capacity: {evt.capacity}</span>}
                          </div>
                        </div>
                        <div style={styles.portalCardRight}>
                          <button
                            onClick={() => handleAddFromCard(evt)}
                            style={styles.trackCardBtn}
                          >
                            <Plus size={13} style={{ marginRight: 4 }} />
                            Track Slot
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ACTIVITY TAB */}
        {activeTab === 'activity' && (
          <div style={styles.tabSection}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h2 style={styles.pageTitle}>Execution Activity & Audit Log</h2>
                <p style={styles.pageSubtitle}>
                  Every autonomous submission attempt, retry, and server response is recorded.
                </p>
              </div>
              <button onClick={fetchAttempts} style={styles.secondaryActionBtn}>
                <RefreshCw size={13} style={{ marginRight: 6 }} />
                Refresh Logs
              </button>
            </div>

            <div style={styles.tableCard}>
              {attempts.length === 0 ? (
                <div style={styles.emptyTable}>No activity records found.</div>
              ) : (
                <div style={styles.compactList}>
                  {attempts.map((att) => (
                    <div key={att.id} style={styles.activityRow}>
                      <div style={styles.activityLeft}>
                        <div style={styles.activityHeader}>
                          <span style={styles.activityTitle}>
                            Attempt #{att.id} — Session {att.session_id || 'N/A'}
                          </span>
                          <span
                            style={{
                              ...styles.statusBadge,
                              ...getAttemptBadgeStyle(att.status)
                            }}
                          >
                            {att.status}
                          </span>
                          {att.verified && <span style={styles.verifiedBadge}>✓ Verified</span>}
                        </div>
                        <p style={styles.activityMsg}>
                          {att.response_message || 'No additional response message from server.'}
                        </p>
                        <div style={styles.activityMeta}>
                          <span>🕒 {att.attempted_at ? new Date(att.attempted_at).toLocaleString() : 'N/A'}</span>
                          <span>Mode: {att.mode}</span>
                          <span>Retries: {att.retry_count || 0}</span>
                          {att.execution_duration_ms && <span>Duration: {att.execution_duration_ms}ms</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* SETTINGS TAB */}
        {activeTab === 'settings' && (
          <div style={styles.tabSection}>
            <div style={styles.sectionHeaderRow}>
              <div>
                <h2 style={styles.pageTitle}>System Configuration</h2>
                <p style={styles.pageSubtitle}>
                  Saveetha College provider settings and local daemon state.
                </p>
              </div>
            </div>

            <div style={styles.settingsGrid}>
              <div style={styles.settingsCard}>
                <h3 style={styles.settingsGroupTitle}>Provider Integration</h3>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Target Portal</span>
                  <span style={styles.settingsValue}>Saveetha Learner Portal</span>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Portal URL</span>
                  <a
                    href="https://learner.saveetha.in/academicevents/event-booking/"
                    target="_blank"
                    rel="noreferrer"
                    style={styles.settingsLink}
                  >
                    learner.saveetha.in
                    <ExternalLink size={12} style={{ marginLeft: 4 }} />
                  </a>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Authentication State</span>
                  <span
                    style={{
                      color: sessionStatus.authenticated ? '#10b981' : '#ef4444',
                      fontWeight: 600
                    }}
                  >
                    {sessionStatus.authenticated ? 'Authenticated Session' : 'Session Expired'}
                  </span>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>FirstShot Account</span>
                  <span style={styles.settingsValue}>
                    {currentUser?.username || 'Not Signed In'} ({currentUser?.role === 'owner' ? 'Workstation Owner' : 'Student'})
                  </span>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Isolated Profile Path</span>
                  <span style={{ ...styles.settingsValue, fontSize: 11, color: '#a1a1aa' }}>
                    {sessionStatus.profile_dir || (currentUser?.role === 'owner' ? '.local/saveetha-profile' : `.local/profiles/user_${currentUser?.id}`)}
                  </span>
                </div>
                <div style={{ marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <button onClick={() => setShowRemoteAuthModal(true)} style={styles.primaryActionBtn}>
                    <Monitor size={14} style={{ marginRight: 6 }} />
                    Interactive Remote Portal Login
                  </button>
                  {currentUser?.role === 'owner' && (
                    <button onClick={handleReauthenticate} style={styles.secondaryActionBtn}>
                      <ExternalLink size={14} style={{ marginRight: 6 }} />
                      Launch Local Host Browser
                    </button>
                  )}
                </div>
              </div>

              <div style={styles.settingsCard}>
                <h3 style={styles.settingsGroupTitle}>Autonomous Scheduler Specs</h3>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Timezone</span>
                  <span style={styles.settingsValue}>Asia/Kolkata (IST)</span>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Opening Surge Window</span>
                  <span style={styles.settingsValue}>19:00:00 IST (Daily)</span>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Blitz Polling Window</span>
                  <span style={styles.settingsValue}>18:59:45 – 19:05:00 IST (2s cadence)</span>
                </div>
                <div style={styles.settingsRow}>
                  <span style={styles.settingsLabel}>Crash-Surge Retry Window</span>
                  <span style={styles.settingsValue}>300 seconds (5 minutes continuous)</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* PRE-ARM MODAL */}
      {armModalTarget && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalCard}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>Pre-Arm Autonomous Booking</h3>
              <button onClick={() => setArmModalTarget(null)} style={styles.modalCloseBtn}>
                ✕
              </button>
            </div>

            <div style={styles.modalBody}>
              <div style={styles.modalTargetSummary}>
                <div style={{ fontWeight: 600, color: '#fff', fontSize: 15 }}>
                  {armModalTarget.event_title}
                </div>
                <div style={{ color: '#888', fontSize: 13, marginTop: 4 }}>
                  📅 {armModalTarget.target_date} · 🏢 Room {armModalTarget.preferred_room} · ⏰{' '}
                  {armModalTarget.preferred_start_time} - {armModalTarget.preferred_end_time}
                </div>
              </div>

              <div style={styles.inputGroup}>
                <label style={styles.inputLabel}>Booking Purpose (College Requirement)</label>
                <input
                  type="text"
                  value={armPurpose}
                  onChange={(e) => setArmPurpose(e.target.value)}
                  style={styles.textInput}
                />
              </div>

              <div style={styles.checkboxGroup}>
                <label style={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={armAcceptWaitlist}
                    onChange={(e) => setArmAcceptWaitlist(e.target.checked)}
                    style={{ marginRight: 8 }}
                  />
                  Accept Waitlist if session is full
                </label>
              </div>

              <div style={styles.consentBox}>
                <label style={styles.consentLabel}>
                  <input
                    type="checkbox"
                    checked={armUserConsent}
                    onChange={(e) => setArmUserConsent(e.target.checked)}
                    style={{ marginRight: 8, marginTop: 2 }}
                  />
                  <span>
                    I confirm that I authorize FirstShot to autonomously submit this booking attempt on
                    my authenticated account when availability opens at 7:00 PM IST.
                  </span>
                </label>
              </div>
            </div>

            <div style={styles.modalFooter}>
              <button onClick={() => setArmModalTarget(null)} style={styles.secondaryActionBtn}>
                Cancel
              </button>
              <button
                onClick={handleArmTarget}
                disabled={!armUserConsent || armingLoading}
                style={styles.armConfirmBtn}
              >
                {armingLoading ? 'Arming Engine...' : 'Confirm & Arm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PREFLIGHT RESULT MODAL */}
      {preflightResult && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalCardWide}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>8-Point Preflight Audit</h3>
              <button onClick={() => setPreflightResult(null)} style={styles.modalCloseBtn}>
                ✕
              </button>
            </div>

            <div style={styles.modalBody}>
              <div
                style={{
                  ...styles.preflightSummaryBox,
                  backgroundColor: preflightResult.passed ? '#064e3b' : '#7f1d1d'
                }}
              >
                <div style={{ fontWeight: 600 }}>{preflightResult.summary}</div>
              </div>

              <div style={styles.preflightList}>
                {preflightResult.checks.map((c, idx) => (
                  <div key={idx} style={styles.preflightItem}>
                    {c.passed ? (
                      <CheckCircle2 size={16} style={{ color: '#10b981', minWidth: 16 }} />
                    ) : (
                      <XCircle size={16} style={{ color: '#ef4444', minWidth: 16 }} />
                    )}
                    <div style={{ flex: 1, marginLeft: 10 }}>
                      <div style={styles.preflightName}>{c.name}</div>
                      <div style={styles.preflightDetail}>{c.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={styles.modalFooter}>
              <button onClick={() => setPreflightResult(null)} style={styles.primaryActionBtn}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ADD TARGET MODAL */}
      {showAddModal && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalCard}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>Configure Target Assessment</h3>
              <button onClick={() => setShowAddModal(false)} style={styles.modalCloseBtn}>
                ✕
              </button>
            </div>

            <form onSubmit={handleAddManualTarget} style={styles.modalBody}>
              <div style={styles.inputGroup}>
                <label style={styles.inputLabel}>Assessment Title</label>
                <input
                  type="text"
                  value={manualTitle}
                  onChange={(e) => setManualTitle(e.target.value)}
                  style={styles.textInput}
                  required
                />
              </div>

              <div style={styles.inputGroup}>
                <label style={styles.inputLabel}>Target Date</label>
                <input
                  type="date"
                  value={manualDate}
                  onChange={(e) => setManualDate(e.target.value)}
                  style={styles.textInput}
                  required
                />
              </div>

              <div style={styles.inputGroup}>
                <label style={styles.inputLabel}>Preferred Room</label>
                <input
                  type="text"
                  value={manualRoom}
                  onChange={(e) => setManualRoom(e.target.value)}
                  placeholder="e.g. 1731, 1851, 1852"
                  style={styles.textInput}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1, ...styles.inputGroup }}>
                  <label style={styles.inputLabel}>Start Time</label>
                  <input
                    type="time"
                    value={manualStartTime}
                    onChange={(e) => setManualStartTime(e.target.value)}
                    style={styles.textInput}
                    required
                  />
                </div>
                <div style={{ flex: 1, ...styles.inputGroup }}>
                  <label style={styles.inputLabel}>End Time</label>
                  <input
                    type="time"
                    value={manualEndTime}
                    onChange={(e) => setManualEndTime(e.target.value)}
                    style={styles.textInput}
                    required
                  />
                </div>
              </div>

              <div style={styles.modalFooter}>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  style={styles.secondaryActionBtn}
                >
                  Cancel
                </button>
                <button type="submit" style={styles.primaryActionBtn}>
                  Save Target
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* FIRSTSHOT AUTHENTICATION MODAL */}
      {showAuthModal && (
        <div style={styles.modalOverlay}>
          <div style={{ ...styles.modalCard, maxWidth: 420 }}>
            <div style={styles.modalHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={styles.logoBadge}>FS</div>
                <h3 style={styles.modalTitle}>
                  {authMode === 'login' ? 'Sign in to FirstShot' : 'Create Student Account'}
                </h3>
              </div>
              {currentUser && (
                <button onClick={() => setShowAuthModal(false)} style={styles.modalCloseBtn}>
                  ✕
                </button>
              )}
            </div>

            <form onSubmit={handleAuthSubmit}>
              <div style={styles.modalBody}>
                {authError && (
                  <div style={{ padding: '8px 12px', background: '#7f1d1d33', border: '1px solid #7f1d1d88', borderRadius: 6, color: '#f87171', fontSize: 13, marginBottom: 12 }}>
                    {authError}
                  </div>
                )}

                <div style={{ display: 'flex', borderBottom: '1px solid #27272a', marginBottom: 16 }}>
                  <button
                    type="button"
                    onClick={() => { setAuthMode('login'); setAuthError(''); }}
                    style={{
                      flex: 1,
                      padding: '8px 0',
                      background: 'none',
                      border: 'none',
                      borderBottom: authMode === 'login' ? '2px solid #6366f1' : 'none',
                      color: authMode === 'login' ? '#fff' : '#a1a1aa',
                      fontWeight: 600,
                      cursor: 'pointer',
                      fontSize: 13
                    }}
                  >
                    Sign In
                  </button>
                  <button
                    type="button"
                    onClick={() => { setAuthMode('register'); setAuthError(''); }}
                    style={{
                      flex: 1,
                      padding: '8px 0',
                      background: 'none',
                      border: 'none',
                      borderBottom: authMode === 'register' ? '2px solid #6366f1' : 'none',
                      color: authMode === 'register' ? '#fff' : '#a1a1aa',
                      fontWeight: 600,
                      cursor: 'pointer',
                      fontSize: 13
                    }}
                  >
                    Register
                  </button>
                </div>

                <div style={styles.inputGroup}>
                  <label style={styles.inputLabel}>Username</label>
                  <input
                    type="text"
                    required
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                    placeholder="e.g. 192201001 or alice"
                    style={styles.textInput}
                    autoFocus
                  />
                </div>

                <div style={styles.inputGroup}>
                  <label style={styles.inputLabel}>Password</label>
                  <input
                    type="password"
                    required
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    placeholder="Enter account password"
                    style={styles.textInput}
                  />
                </div>

                <p style={{ fontSize: 12, color: '#71717a', marginTop: 4, lineHeight: 1.4 }}>
                  {authMode === 'login'
                    ? 'Log in to access your isolated Saveetha portal session, personal targets, and booking history.'
                    : 'Each registered student receives an isolated browser worker, independent cookies, and secure personal targets.'}
                </p>
              </div>

              <div style={styles.modalFooter}>
                <button
                  type="submit"
                  disabled={authLoading}
                  style={{ ...styles.primaryActionBtn, width: '100%', justifyContent: 'center' }}
                >
                  {authLoading
                    ? 'Authenticating...'
                    : authMode === 'login'
                    ? 'Sign In'
                    : 'Create Account & Sign In'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* REMOTE INTERACTIVE BROWSER LOGIN MODAL */}
      {showRemoteAuthModal && (
        <div style={styles.modalOverlay}>
          <div style={{ ...styles.modalCardWide, maxWidth: 1060, width: '96vw' }}>
            <div style={styles.modalHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Monitor size={18} style={{ color: '#6366f1' }} />
                <div>
                  <h3 style={styles.modalTitle}>Saveetha Portal Remote Login</h3>
                  <div style={{ fontSize: 12, color: '#a1a1aa', marginTop: 2 }}>
                    {remoteStatus}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setShowRemoteAuthModal(false)}
                style={styles.modalCloseBtn}
                title="Close remote session"
              >
                ✕
              </button>
            </div>

            <div style={{ padding: 12, backgroundColor: '#09090b', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{
                position: 'relative',
                width: '100%',
                maxWidth: 1024,
                aspectRatio: '1024 / 768',
                backgroundColor: '#18181b',
                borderRadius: 6,
                overflow: 'hidden',
                border: '1px solid #27272a',
                boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
              }}>
                <canvas
                  ref={canvasRef}
                  width={1024}
                  height={768}
                  tabIndex={0}
                  onMouseDown={(e) => sendRemoteMouseEvent('mousePressed', e)}
                  onMouseUp={(e) => sendRemoteMouseEvent('mouseReleased', e)}
                  onMouseMove={(e) => sendRemoteMouseEvent('mouseMoved', e)}
                  onKeyDown={(e) => sendRemoteKeyEvent('keyDown', e)}
                  onKeyUp={(e) => sendRemoteKeyEvent('keyUp', e)}
                  onContextMenu={(e) => e.preventDefault()}
                  style={{
                    width: '100%',
                    height: '100%',
                    display: 'block',
                    cursor: 'pointer',
                    outline: 'none'
                  }}
                />
              </div>

              <div style={{ marginTop: 10, display: 'flex', justifyContent: 'space-between', width: '100%', maxWidth: 1024, fontSize: 12, color: '#71717a' }}>
                <span>🔒 Secure headless browser profile isolated to user #{currentUser?.id} ({currentUser?.username}).</span>
                <span>Click inside the window and enter your credentials. Session auto-saves on login.</span>
              </div>
            </div>

            <div style={styles.modalFooter}>
              <button
                onClick={() => {
                  fetchSession();
                  setShowRemoteAuthModal(false);
                }}
                style={styles.secondaryActionBtn}
              >
                Done / Close Window
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div
          style={{
            ...styles.toastCard,
            borderLeft: `4px solid ${
              toast.type === 'success'
                ? '#10b981'
                : toast.type === 'error'
                ? '#ef4444'
                : toast.type === 'warning'
                ? '#f59e0b'
                : '#6366f1'
            }`
          }}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}

// Helpers for status badges
function getStatusBadgeStyle(status) {
  switch (status) {
    case 'Open':
      return { backgroundColor: '#064e3b', color: '#34d399' };
    case 'Booked':
      return { backgroundColor: '#312e81', color: '#a5b4fc' };
    case 'Opening Soon':
      return { backgroundColor: '#78350f', color: '#fcd34d' };
    case 'Full':
      return { backgroundColor: '#7f1d1d', color: '#f87171' };
    default:
      return { backgroundColor: '#262626', color: '#a3a3a3' };
  }
}

function getAttemptBadgeStyle(status) {
  switch (status) {
    case 'CONFIRMED':
      return { backgroundColor: '#064e3b', color: '#34d399' };
    case 'FAILED':
      return { backgroundColor: '#7f1d1d', color: '#f87171' };
    case 'RETRYING':
      return { backgroundColor: '#78350f', color: '#fcd34d' };
    case 'INITIATED':
      return { backgroundColor: '#1e3a8a', color: '#93c5fd' };
    default:
      return { backgroundColor: '#262626', color: '#a3a3a3' };
  }
}

const styles = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#0a0a0a',
    color: '#e5e5e5',
    display: 'flex',
    flexDirection: 'column'
  },
  header: {
    height: 56,
    borderBottom: '1px solid #1f1f1f',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 24px',
    backgroundColor: '#0a0a0a'
  },
  navLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 16
  },
  logoBadge: {
    width: 28,
    height: 28,
    borderRadius: 6,
    backgroundColor: '#6366f1',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: 13,
    letterSpacing: -0.5
  },
  logoTitle: {
    fontWeight: 600,
    fontSize: 15,
    color: '#fff'
  },
  versionBadge: {
    fontSize: 11,
    color: '#737373',
    backgroundColor: '#171717',
    padding: '2px 6px',
    borderRadius: 4,
    border: '1px solid #262626'
  },
  navLinks: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    marginLeft: 16
  },
  navButton: {
    background: 'none',
    border: 'none',
    color: '#888',
    padding: '6px 12px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    transition: 'all 0.15s ease'
  },
  navButtonActive: {
    backgroundColor: '#171717',
    color: '#fff'
  },
  pillCount: {
    fontSize: 10,
    backgroundColor: '#262626',
    color: '#aaa',
    padding: '1px 5px',
    borderRadius: 8
  },
  navRight: {
    display: 'flex',
    alignItems: 'center',
    gap: 12
  },
  sessionStatus: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 12,
    color: '#a3a3a3'
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: '50%'
  },
  statusLabel: {
    fontSize: 12,
    fontWeight: 500
  },
  mainContent: {
    flex: 1,
    maxWidth: 1080,
    width: '100%',
    margin: '0 auto',
    padding: '32px 24px'
  },
  tabSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 24
  },
  heroCard: {
    backgroundColor: '#121212',
    border: '1px solid #262626',
    borderRadius: 8,
    padding: 24
  },
  heroHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16
  },
  heroLabel: {
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: '#a3a3a3',
    fontWeight: 600
  },
  heroBody: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 16
  },
  heroMainInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8
  },
  heroTitle: {
    fontSize: 22,
    fontWeight: 600,
    color: '#fff',
    margin: 0
  },
  heroMetaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 20,
    color: '#a3a3a3',
    fontSize: 13
  },
  heroMetaItem: {
    display: 'flex',
    alignItems: 'center'
  },
  heroActions: {
    display: 'flex',
    alignItems: 'center',
    gap: 10
  },
  heroArmBtn: {
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    padding: '8px 16px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center',
    transition: 'background-color 0.15s ease'
  },
  heroDisarmBtn: {
    backgroundColor: '#d97706',
    color: '#fff',
    border: 'none',
    padding: '8px 16px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center'
  },
  heroSecondaryBtn: {
    backgroundColor: '#1e1e1e',
    color: '#d4d4d4',
    border: '1px solid #333',
    padding: '8px 14px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center'
  },
  emptyHero: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '24px 0'
  },
  addBtnSmall: {
    backgroundColor: '#1f1f1f',
    color: '#e5e5e5',
    border: '1px solid #333',
    padding: '6px 12px',
    borderRadius: 6,
    fontSize: 12,
    marginTop: 8,
    display: 'flex',
    alignItems: 'center'
  },
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: 14
  },
  metricCard: {
    backgroundColor: '#121212',
    border: '1px solid #262626',
    borderRadius: 8,
    padding: 16,
    display: 'flex',
    flexDirection: 'column'
  },
  metricLabel: {
    fontSize: 11,
    color: '#737373',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    fontWeight: 600
  },
  metricVal: {
    fontSize: 22,
    fontWeight: 700,
    color: '#fff',
    margin: '4px 0'
  },
  metricSub: {
    fontSize: 12,
    color: '#888'
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 8
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: '#fff',
    margin: 0
  },
  refreshIconBtn: {
    background: 'none',
    border: '1px solid #262626',
    color: '#888',
    padding: '6px 8px',
    borderRadius: 6
  },
  sectionHeaderRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4
  },
  pageTitle: {
    fontSize: 18,
    fontWeight: 600,
    color: '#fff',
    margin: 0
  },
  pageSubtitle: {
    fontSize: 13,
    color: '#888',
    marginTop: 2
  },
  tableCard: {
    backgroundColor: '#121212',
    border: '1px solid #262626',
    borderRadius: 8,
    overflow: 'hidden'
  },
  emptyTable: {
    padding: 32,
    textAlign: 'center',
    color: '#737373',
    fontSize: 13
  },
  compactList: {
    display: 'flex',
    flexDirection: 'column'
  },
  compactRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '14px 18px',
    borderBottom: '1px solid #1a1a1a'
  },
  compactColLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4
  },
  compactTitle: {
    fontSize: 14,
    fontWeight: 500,
    color: '#fff'
  },
  compactSubtitle: {
    fontSize: 12,
    color: '#737373'
  },
  compactColRight: {
    display: 'flex',
    alignItems: 'center',
    gap: 10
  },
  statusBadge: {
    fontSize: 11,
    fontWeight: 600,
    padding: '3px 8px',
    borderRadius: 4
  },
  durationPill: {
    fontSize: 11,
    color: '#737373',
    backgroundColor: '#1c1c1c',
    padding: '2px 6px',
    borderRadius: 4
  },
  targetRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 20px',
    borderBottom: '1px solid #1a1a1a'
  },
  targetInfoCol: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6
  },
  targetTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10
  },
  targetName: {
    fontSize: 15,
    fontWeight: 600,
    color: '#fff'
  },
  modeBadge: {
    fontSize: 10,
    padding: '2px 6px',
    borderRadius: 4,
    backgroundColor: '#262626',
    color: '#a3a3a3',
    fontWeight: 600,
    letterSpacing: 0.5
  },
  modeBadgeAuto: {
    backgroundColor: '#312e81',
    color: '#c7d2fe'
  },
  armedPill: {
    fontSize: 10,
    backgroundColor: '#6366f1',
    color: '#fff',
    padding: '2px 6px',
    borderRadius: 4,
    fontWeight: 700
  },
  targetMetaRow: {
    display: 'flex',
    gap: 16,
    fontSize: 12,
    color: '#888'
  },
  targetActionsCol: {
    display: 'flex',
    alignItems: 'center',
    gap: 8
  },
  actionBtnArm: {
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    padding: '6px 12px',
    borderRadius: 5,
    fontSize: 12,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center'
  },
  actionBtnDisarm: {
    backgroundColor: '#d97706',
    color: '#fff',
    border: 'none',
    padding: '6px 12px',
    borderRadius: 5,
    fontSize: 12,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center'
  },
  actionBtnIcon: {
    backgroundColor: '#1f1f1f',
    color: '#d4d4d4',
    border: '1px solid #333',
    padding: '6px 8px',
    borderRadius: 5
  },
  actionBtnDanger: {
    backgroundColor: 'transparent',
    color: '#ef4444',
    border: '1px solid #3f1515',
    padding: '6px 8px',
    borderRadius: 5
  },
  portalCardRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '14px 18px',
    borderBottom: '1px solid #1a1a1a'
  },
  portalCardLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4
  },
  portalCardTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10
  },
  portalCardTitle: {
    fontSize: 14,
    fontWeight: 500,
    color: '#fff'
  },
  portalCardRight: {
    display: 'flex',
    alignItems: 'center'
  },
  trackCardBtn: {
    backgroundColor: '#1e1e1e',
    color: '#e5e5e5',
    border: '1px solid #333',
    padding: '5px 12px',
    borderRadius: 5,
    fontSize: 12,
    display: 'flex',
    alignItems: 'center'
  },
  activityRow: {
    padding: '16px 20px',
    borderBottom: '1px solid #1a1a1a'
  },
  activityLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6
  },
  activityHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10
  },
  activityTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: '#fff'
  },
  verifiedBadge: {
    fontSize: 10,
    backgroundColor: '#064e3b',
    color: '#34d399',
    padding: '2px 6px',
    borderRadius: 4
  },
  activityMsg: {
    fontSize: 13,
    color: '#ccc',
    margin: 0
  },
  activityMeta: {
    display: 'flex',
    gap: 16,
    fontSize: 11,
    color: '#737373'
  },
  settingsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
    gap: 20
  },
  settingsCard: {
    backgroundColor: '#121212',
    border: '1px solid #262626',
    borderRadius: 8,
    padding: 20
  },
  settingsGroupTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: '#fff',
    marginTop: 0,
    marginBottom: 16
  },
  settingsRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '10px 0',
    borderBottom: '1px solid #1c1c1c',
    fontSize: 13
  },
  settingsLabel: {
    color: '#888'
  },
  settingsValue: {
    color: '#fff',
    fontWeight: 500
  },
  settingsLink: {
    color: '#6366f1',
    display: 'flex',
    alignItems: 'center'
  },
  primaryActionBtn: {
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    padding: '7px 14px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center'
  },
  secondaryActionBtn: {
    backgroundColor: '#1e1e1e',
    color: '#d4d4d4',
    border: '1px solid #333',
    padding: '7px 14px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center'
  },
  dateInput: {
    backgroundColor: '#171717',
    border: '1px solid #2c2c2c',
    color: '#fff',
    padding: '6px 10px',
    borderRadius: 5,
    fontSize: 12
  },
  selectInput: {
    backgroundColor: '#171717',
    border: '1px solid #2c2c2c',
    color: '#fff',
    padding: '6px 10px',
    borderRadius: 5,
    fontSize: 12
  },
  modalOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.75)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    padding: 20
  },
  modalCard: {
    backgroundColor: '#121212',
    border: '1px solid #262626',
    borderRadius: 8,
    width: '100%',
    maxWidth: 480,
    overflow: 'hidden'
  },
  modalCardWide: {
    backgroundColor: '#121212',
    border: '1px solid #262626',
    borderRadius: 8,
    width: '100%',
    maxWidth: 620,
    overflow: 'hidden'
  },
  modalHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 20px',
    borderBottom: '1px solid #1f1f1f'
  },
  modalTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: '#fff',
    margin: 0
  },
  modalCloseBtn: {
    background: 'none',
    border: 'none',
    color: '#888',
    fontSize: 16
  },
  modalBody: {
    padding: 20,
    display: 'flex',
    flexDirection: 'column',
    gap: 16
  },
  modalTargetSummary: {
    backgroundColor: '#181818',
    padding: 12,
    borderRadius: 6,
    border: '1px solid #262626'
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6
  },
  inputLabel: {
    fontSize: 12,
    color: '#a3a3a3',
    fontWeight: 500
  },
  textInput: {
    backgroundColor: '#181818',
    border: '1px solid #2e2e2e',
    color: '#fff',
    padding: '8px 12px',
    borderRadius: 5,
    fontSize: 13
  },
  checkboxGroup: {
    display: 'flex',
    alignItems: 'center'
  },
  checkboxLabel: {
    fontSize: 13,
    color: '#d4d4d4',
    display: 'flex',
    alignItems: 'center'
  },
  consentBox: {
    backgroundColor: '#1c1917',
    border: '1px solid #44281d',
    padding: 12,
    borderRadius: 6
  },
  consentLabel: {
    fontSize: 12,
    color: '#fdba74',
    display: 'flex',
    lineHeight: 1.4
  },
  modalFooter: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 10,
    padding: '14px 20px',
    borderTop: '1px solid #1f1f1f',
    backgroundColor: '#0d0d0d'
  },
  armConfirmBtn: {
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    padding: '8px 16px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500
  },
  preflightSummaryBox: {
    padding: 12,
    borderRadius: 6,
    color: '#fff',
    fontSize: 13
  },
  preflightList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12
  },
  preflightItem: {
    display: 'flex',
    alignItems: 'flex-start',
    padding: '8px 0',
    borderBottom: '1px solid #1a1a1a'
  },
  preflightName: {
    fontSize: 13,
    fontWeight: 600,
    color: '#fff'
  },
  preflightDetail: {
    fontSize: 12,
    color: '#888',
    marginTop: 2
  },
  toastCard: {
    position: 'fixed',
    bottom: 24,
    right: 24,
    backgroundColor: '#171717',
    border: '1px solid #2a2a2a',
    borderRadius: 6,
    padding: '12px 18px',
    color: '#fff',
    fontSize: 13,
    boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
    zIndex: 2000,
    maxWidth: 380
  }
};
