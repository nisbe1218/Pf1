import React, { useEffect, useState, useMemo, useCallback } from 'react';
import api from '../../services/api/axios';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { useContext } from 'react';
import { AuthContext } from '../../context/AuthContext';
import { useLanguage } from '../../context/LanguageContext';

export const SIDEBAR_W = 248;

/* ── Palette matching Hero gradient ─────────────────────────────────────────── */
const C = {
  /* Fond sidebar — même dégradé que le header */
  bg: 'linear-gradient(180deg, #C2DFF0 0%, #BCD8EE 60%, #CEC0E0 82%, #ECC5D2 100%)',
  shadow: '4px 0 28px rgba(0,0,0,0.08)',
  border: '1px solid rgba(255,255,255,0.50)',

  /* Carte nav */
  cardBg: 'rgba(255,255,255,0.45)',
  cardRadius: 16,

  /* Bouton actif */
  activeBg:   '#FDF0F3',
  activeTxt:  '#C46B82',
  activeIcon: '#C46B82',

  /* Hover */
  hoverBg:  'rgba(255,255,255,0.55)',
  hoverTxt: '#1E293B',
  hoverIcon:'#1A6B8A',

  /* Texte et icônes repos */
  txt:  '#2D4A5A',
  icon: '#4A7A8A',

  /* Header titre */
  headTxt: '#0D3A4A',

  /* Pill profil */
  pillBg:  'rgba(255,255,255,0.50)',
  pillTxt: '#1E293B',
  pillIcon:'#4A7A8A',

  /* Badge compteur */
  badgeBg:  '#FAE8ED',
  badgeTxt: '#C46B82',

  /* Séparateur */
  sep: 'rgba(255,255,255,0.40)',

  /* Popover notif */
  deepNavy:'#0A2B3E', softRose:'#D47A8E', dustyRose:'#C46B82',
  textMuted:'#6B8A9C', textDark:'#1A2F3C', medBlue:'#1A6B8A', oceanT:'#2C8C9E',
};

/* ── Icons ────────────────────────────────────────────────────────────────── */
const IconDashboard = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>;
const IconPatients  = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;
const IconAI        = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>;
const IconMonitor   = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/><path d="M8 20h8M12 17v3M7 12h2l1.2-3 2.1 6 1.6-3H17"/></svg>;
const IconBell = (s=18) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
const IconPreprocess = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="12" y2="17"/></svg>;
const IconValidate   = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>;
const IconLogout    = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>;
const IconProfile   = <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>;
const IconMenu      = <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>;
const IconClose     = <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;

/* ── NavItem ─────────────────────────────────────────────────────────────── */
function NavItem({ icon, label, active, onClick, count }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 11,
        width: 'calc(100% - 10px)', margin: '2px 5px',
        padding: '11px 14px',
        borderRadius: 12,
        background: active ? C.activeBg : hov ? C.hoverBg : 'transparent',
        border: 'none',
        boxShadow: 'none',
        outline: 'none', cursor: 'pointer', textAlign: 'left',
        color: active ? C.activeTxt : hov ? C.hoverTxt : C.txt,
        fontSize: 14, fontWeight: active ? 600 : 400,
        transition: 'background 0.15s ease, color 0.15s ease',
      }}
    >
      <span style={{
        flexShrink: 0,
        color: active ? C.activeIcon : hov ? C.hoverIcon : C.icon,
        transition: 'color 0.15s',
        display: 'flex', alignItems: 'center',
      }}>
        {icon}
      </span>
      <span style={{ flex: 1, letterSpacing: '-0.01em' }}>{label}</span>
      {count > 0 && (
        <span style={{
          minWidth: 22, height: 22, borderRadius: 40, flexShrink: 0,
          padding: '0 7px',
          background: C.badgeBg,
          color: C.badgeTxt,
          fontSize: 11, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {count > 9 ? '9+' : count}
        </span>
      )}
    </button>
  );
}

function BottomIllustration() { return null; }

/* ── NotifPopover ──────────────────────────────────────────────────────────── */
function NotifPopover({ anchor, onClose, pendingValidations, onValidate, approvingId }) {
  if (!anchor) return null;
  const PANEL_W = 360, hasPending = pendingValidations && pendingValidations.length > 0;
  const vw = window.innerWidth, vh = window.innerHeight;
  const estimatedH = hasPending ? Math.min(140 + pendingValidations.length * 158, 520) : 240;
  let left = anchor.right + 14; if (left + PANEL_W > vw - 12) left = vw - PANEL_W - 12;
  let top = anchor.top + (anchor.height / 2) - estimatedH / 2;
  top = Math.max(12, Math.min(top, vh - estimatedH - 12));
  const arrowY = anchor.top + anchor.height / 2 - 7;
  const fmt = (iso) => { try { const d=new Date(iso),now=new Date(),m=Math.floor((now-d)/60000); if(m<1)return'À l\'instant'; if(m<60)return`Il y a ${m} min`; if(m<1440)return`Il y a ${Math.floor(m/60)}h`; return d.toLocaleDateString('fr-FR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}); } catch{return iso;} };
  const content = (<>
    <div onClick={onClose} style={{position:'fixed',inset:0,zIndex:9000}}/>
    <div style={{position:'fixed',top:arrowY,left:anchor.right+5,width:13,height:13,background:'#fff',transform:'rotate(45deg)',zIndex:9002,boxShadow:'-2px -2px 6px rgba(0,0,0,0.06)',borderLeft:'1px solid #e4eaf0',borderTop:'1px solid #e4eaf0'}}/>
    <div style={{position:'fixed',top,left,width:PANEL_W,zIndex:9001,borderRadius:20,background:'#fff',boxShadow:'0 12px 48px rgba(10,43,62,0.16)',border:'1px solid #e4eaf0',overflow:'hidden',animation:'notifIn 0.2s ease-out'}}>
      <div style={{padding:'16px 18px 14px',borderBottom:'1px solid #f0f4f8',display:'flex',alignItems:'center',justifyContent:'space-between',background:hasPending?'linear-gradient(135deg,#fff5f7,#fdf4ff)':'linear-gradient(135deg,#f0fdf9,#f0f9ff)'}}>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <div style={{width:40,height:40,borderRadius:12,background:hasPending?'linear-gradient(135deg,#D47A8E30,#9B59B620)':'linear-gradient(135deg,#d1fae5,#dbeafe)',display:'flex',alignItems:'center',justifyContent:'center',color:hasPending?C.softRose:'#10B981'}}>{IconBell(17)}</div>
          <div>
            <div style={{fontWeight:700,fontSize:15,color:C.deepNavy}}>Notifications</div>
            <div style={{display:'flex',alignItems:'center',gap:5,marginTop:3}}>
              <div style={{width:7,height:7,borderRadius:'50%',background:hasPending?'#F59E0B':'#10B981',animation:hasPending?'pulse 1.8s infinite':'none'}}/>
              <span style={{fontSize:12,color:C.textMuted,fontWeight:500}}>{hasPending?`${pendingValidations.length} import(s) en attente`:'Tout est à jour'}</span>
            </div>
          </div>
        </div>
        <button onClick={onClose} style={{width:30,height:30,borderRadius:8,border:'1px solid #e4eaf0',background:'#f8fafc',cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center',color:C.textMuted}} onMouseEnter={e=>e.currentTarget.style.background='#eef2f6'} onMouseLeave={e=>e.currentTarget.style.background='#f8fafc'}>{IconClose}</button>
      </div>
      <div style={{maxHeight:400,overflowY:'auto',padding:'14px 16px 16px',background:'#fafcfe'}}>
        {hasPending?(
          <div style={{display:'flex',flexDirection:'column',gap:10}}>
            {pendingValidations.map(v=>(
              <div key={v.id} style={{borderRadius:14,background:'#fff',border:`1.5px solid ${C.softRose}28`,overflow:'hidden'}}>
                <div style={{height:3,background:`linear-gradient(90deg,${C.softRose},#8B5CF6)`}}/>
                <div style={{padding:'12px 14px'}}>
                  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:8}}>
                    <span style={{display:'inline-flex',alignItems:'center',gap:4,background:`${C.softRose}12`,border:`1px solid ${C.softRose}28`,borderRadius:20,padding:'2px 9px',fontSize:11,fontWeight:600,color:C.dustyRose}}><div style={{width:5,height:5,borderRadius:'50%',background:C.softRose,animation:'pulse 1.5s infinite'}}/>Import en attente</span>
                    <span style={{fontSize:11,color:C.textMuted}}>{v.submitted_at?fmt(v.submitted_at):''}</span>
                  </div>
                  <div style={{fontSize:13,fontWeight:600,color:C.deepNavy,marginBottom:3}}>{v.source_file_name||'Fichier importé'}</div>
                  <div style={{fontSize:12,color:C.textMuted}}>Par <strong style={{color:C.textDark}}>{typeof v.submitted_by==='object'?(v.submitted_by?.username||v.submitted_by?.first_name||'Utilisateur'):(v.submitted_by||'Utilisateur')}</strong>{v.rows_count?` · ${v.rows_count} lignes`:''}</div>
                  <button onClick={()=>onValidate(v.id)} disabled={approvingId===v.id} style={{marginTop:10,width:'100%',padding:'9px 0',borderRadius:10,border:'none',background:approvingId===v.id?'#f1f5f9':`linear-gradient(135deg,${C.medBlue},${C.oceanT})`,color:approvingId===v.id?C.textMuted:'#fff',fontWeight:600,fontSize:13,cursor:approvingId===v.id?'wait':'pointer',display:'flex',alignItems:'center',justifyContent:'center',gap:6}} onMouseEnter={e=>{if(approvingId!==v.id)e.currentTarget.style.filter='brightness(1.08)'}} onMouseLeave={e=>{if(approvingId!==v.id)e.currentTarget.style.filter='none'}}>
                    {approvingId===v.id?'Validation...':(<><svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>Valider et intégrer</>)}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ):(
          <div style={{textAlign:'center',padding:'28px 16px 24px'}}>
            <div style={{width:60,height:60,borderRadius:18,margin:'0 auto 16px',background:'linear-gradient(135deg,#d1fae5,#dbeafe)',display:'flex',alignItems:'center',justifyContent:'center'}}>
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div style={{fontWeight:700,color:C.deepNavy,fontSize:15,marginBottom:6}}>Tout est à jour</div>
            <div style={{fontSize:12,color:C.textMuted,lineHeight:1.7}}>Aucune action en attente.<br/>Vous serez notifié dès qu'un import est soumis.</div>
          </div>
        )}
      </div>
    </div>
    <style>{`@keyframes notifIn{from{opacity:0;transform:translateX(-10px) scale(0.97)}to{opacity:1;transform:translateX(0) scale(1)}}`}</style>
  </>);
  return createPortal(content, document.body);
}

/* ── AppSidebar ─────────────────────────────────────────────────────────── */
function AppSidebar() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const { logout, user } = useContext(AuthContext);
  const isChefOrAdmin = user?.role === 'super_admin' || user?.role === 'chef_service';
  const { t } = useLanguage();
  const [isMobile,   setIsMobile]   = useState(window.innerWidth < 768);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notifAnchor, setNotifAnchor] = useState(null);
  const [pendingValidations, setPendingValidations] = useState([]);
  const [approvingId, setApprovingId] = useState(null);

  useEffect(() => { const fn = () => setIsMobile(window.innerWidth < 768); window.addEventListener('resize', fn); return () => window.removeEventListener('resize', fn); }, []);
  useEffect(() => {
    if (!isChefOrAdmin) { setPendingValidations([]); return; }
    const fetch = async () => { try { const r = await api.get('patients/preprocess/validations/?status=pending&page_size=20'); setPendingValidations(r.data?.results || []); } catch {} };
    fetch(); const iv = setInterval(fetch, 30000); return () => clearInterval(iv);
  }, [isChefOrAdmin]);

  const handleValidate = useCallback(async (id) => {
    setApprovingId(id);
    try { await api.post(`patients/preprocess/validations/${id}/`, { action: 'approve' }); setPendingValidations(p => p.filter(v => v.id !== id)); }
    catch { alert('Erreur lors de la validation.'); } finally { setApprovingId(null); }
  }, []);

  const handleNav = useCallback((path) => { navigate(path); setMobileOpen(false); }, [navigate]);
  const is = useCallback((prefix) => location.pathname.startsWith(prefix), [location.pathname]);

  const navItems = useMemo(() => [
    { icon: IconDashboard, label: t('dashboard'),  path: '/dashboard', active: is('/dashboard') },
    { icon: IconPatients,  label: t('patients'),   path: '/patients',  active: is('/patients') },
    { icon: IconAI,        label: t('aiAnalysis'), path: '/modele-ai', active: is('/modele-ai') },
    { icon: IconMonitor,   label: t('monitor'),    path: '/monitor',   active: is('/monitor') },
  ], [location.pathname, t]);

  const initials = useMemo(() => {
    if (!user) return '?';
    const fn = (user.first_name || '').trim();
    const ln = (user.last_name || '').trim();
    const un = (user.username || '').trim();
    const em = (user.email || '').trim();
    if (fn) return fn[0].toUpperCase();
    if (ln) return ln[0].toUpperCase();
    if (un) return un[0].toUpperCase();
    if (em) return em[0].toUpperCase();
    return '?';
  }, [user]);

  const roleBadge = useMemo(() => ({
    super_admin:'Administrateur', chef_service:'Chef de service',
    professeur:'Professeur', resident:'Résident',
  }[user?.role] || ''), [user]);

  /* ── Corps ────────────────────────────────────────────────────────────── */
  const SidebarContent = ({ onClose }) => (
    <>
      {/* Header */}
      <div style={{ padding: '26px 20px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div
          style={{ fontSize: 15, fontWeight: 800, letterSpacing: '1.4px', textTransform: 'uppercase', cursor: 'pointer', background: 'linear-gradient(135deg, #0D6E8A, #B05070)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', padding: 0 }}
          onClick={() => handleNav('/dashboard')}
        >
          AI NÉPHROCARE
        </div>
        {onClose && (
          <button onClick={onClose} style={{ width: 28, height: 28, borderRadius: 8, border: `1px solid ${C.sep}`, background: C.pillBg, cursor: 'pointer', color: C.txt, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {IconClose}
          </button>
        )}
      </div>

      {/* Carte navigation principale */}
      <div style={{ flex: 1, padding: '16px 12px 0', overflowY: 'auto', position: 'relative', zIndex: 1 }}>
        <div style={{
          background: C.cardBg,
          borderRadius: C.cardRadius,
          padding: '6px 0',
          border: `1px solid ${C.sep}`,
        }}>
          <div style={{ padding: '6px 18px 4px', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: C.icon, textTransform: 'uppercase' }}>
            Navigation
          </div>
          {navItems.map(item => (
            <NavItem key={item.path} icon={item.icon} label={item.label} active={item.active} onClick={() => handleNav(item.path)} />
          ))}
        </div>
      </div>

      {/* Carte utilisateur */}
      <div style={{ padding: '12px 12px 0', flexShrink: 0, position: 'relative', zIndex: 1 }}>
        <div style={{ background: 'rgba(255,255,255,0.92)', borderRadius: C.cardRadius, padding: '12px 14px', border: '1px solid rgba(255,255,255,0.60)', boxShadow: '0 4px 16px rgba(13,77,99,0.10)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'linear-gradient(135deg, #1A8FA8, #D47A8E)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 15, fontWeight: 800, flexShrink: 0, boxShadow: '0 4px 12px rgba(13,77,99,0.20)' }}>
              {initials}
            </div>
            <div style={{ overflow: 'hidden', flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#1E293B', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.email || user?.username || 'Utilisateur'}
              </div>
              <div style={{ fontSize: 11, color: '#7a90a0', marginTop: 1, fontWeight: 500 }}>{roleBadge}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Boutons bas */}
      <div style={{ padding: '8px 12px 16px', flexShrink: 0, position: 'relative', zIndex: 2 }}>
        <div style={{ background: 'rgba(255,255,255,0.75)', borderRadius: C.cardRadius, padding: '4px 0', border: '1px solid rgba(255,255,255,0.55)', boxShadow: '0 2px 10px rgba(13,77,99,0.07)' }}>
          {isChefOrAdmin && (
            <NavItem icon={IconBell(18)} label={t('notifications')} active={false} count={pendingValidations.length}
              onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setNotifAnchor(r); }} />
          )}
          <NavItem icon={IconLogout} label={t('logout')} active={false}
            onClick={() => { logout(); navigate('/login'); }} />
        </div>
      </div>

      <BottomIllustration />
    </>
  );

  const sidebarStyle = {
    background: C.bg,
    borderRadius: '0 28px 28px 0',
    boxShadow: C.shadow,
    borderRight: C.border,
  };

  const Desktop = (
    <nav style={{ position: 'fixed', left: 0, top: 0, height: '100vh', width: SIDEBAR_W, ...sidebarStyle, display: 'flex', flexDirection: 'column', zIndex: 1200, overflow: 'hidden' }}>
      <SidebarContent />
    </nav>
  );

  const Drawer = mobileOpen && (
    <>
      <div onClick={() => setMobileOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.40)', backdropFilter: 'blur(4px)', zIndex: 1299, animation: 'fadeIn 0.2s' }} />
      <div style={{ position: 'fixed', left: 0, top: 0, height: '100%', width: 268, ...sidebarStyle, zIndex: 1300, display: 'flex', flexDirection: 'column', animation: 'slideIn 0.22s cubic-bezier(0.34,1,0.64,1)' }}>
        <SidebarContent onClose={() => setMobileOpen(false)} />
      </div>
    </>
  );

  return (
    <>
      <style>{`
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
        @keyframes fadeIn{from{opacity:0}to{opacity:1}}
        @keyframes slideIn{from{transform:translateX(-100%);opacity:0}to{transform:translateX(0);opacity:1}}
      `}</style>
      {!isMobile && Desktop}
      {isMobile && (
        <button onClick={() => setMobileOpen(true)} style={{ position: 'fixed', top: 14, left: 14, zIndex: 1100, width: 44, height: 44, borderRadius: 12, background: '#fff', border: `1px solid ${C.sep}`, boxShadow: '0 2px 12px rgba(0,0,0,0.10)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.txt }}>
          {IconMenu}
        </button>
      )}
      {Drawer}
      <NotifPopover anchor={notifAnchor} onClose={() => setNotifAnchor(null)} pendingValidations={pendingValidations} onValidate={handleValidate} approvingId={approvingId} />
    </>
  );
}

export default AppSidebar;
