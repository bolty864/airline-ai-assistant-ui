import { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import {
  Avatar, Box, Drawer, Fab, IconButton, InputAdornment, Stack, TextField, Tooltip, Typography,
} from '@mui/material';
import {
  AccountTreeOutlined, ChatOutlined, ChevronLeft, ChevronRight, DashboardOutlined, EditNoteOutlined,
  FlightOutlined, HealthAndSafetyOutlined, HistoryOutlined, HowToRegOutlined, LibraryBooksOutlined,
  ListAltOutlined, MenuBookOutlined, PlayCircleOutline, RssFeedOutlined, SearchOutlined, SettingsOutlined,
  TaskAltOutlined, WarningAmberOutlined,
} from '@mui/icons-material';
import CopilotPanel from './CopilotPanel.jsx';

const EXPANDED = 272;
const COLLAPSED = 84;

const SECTIONS = [
  { label: 'Overview', color: '#A5D8FF', items: [{ to: '/', text: 'Dashboard', icon: DashboardOutlined }] },
  {
    label: 'Regulatory intelligence', color: '#AFD0D6',
    items: [
      { to: '/feed', text: 'Regulatory feed', icon: RssFeedOutlined },
      { to: '/regulations', text: 'Regulations repository', icon: LibraryBooksOutlined },
    ],
  },
  {
    label: 'Compliance analysis', color: '#BFB6BB',
    items: [
      { to: '/obligations', text: 'Obligations', icon: ListAltOutlined },
      { to: '/mapping', text: 'Policy mapping', icon: AccountTreeOutlined },
      { to: '/gaps', text: 'Gap analysis', icon: WarningAmberOutlined },
    ],
  },
  {
    label: 'Remediation', color: '#C49799',
    items: [
      { to: '/drafts', text: 'AI policy drafts', icon: EditNoteOutlined },
      { to: '/tasks', text: 'Tasks & action plans', icon: TaskAltOutlined },
      { to: '/approvals', text: 'Approvals', icon: HowToRegOutlined },
    ],
  },
  { label: 'Knowledge hub', color: '#D9CFD5', items: [{ to: '/knowledge', text: 'Policies, SOPs & controls', icon: MenuBookOutlined }] },
  {
    label: 'Operations', color: '#8FC3EA',
    items: [
      { to: '/audit', text: 'Audit trail', icon: HistoryOutlined },
      { to: '/health', text: 'Repository health', icon: HealthAndSafetyOutlined },
      { to: '/copilot', text: 'AI copilot chat', icon: ChatOutlined },
      { to: '/demo', text: 'Demo mode', icon: PlayCircleOutline },
    ],
  },
  { label: 'Admin', color: '#9A9399', items: [{ to: '/settings', text: 'Sources, users & config', icon: SettingsOutlined }] },
];

const ALL_ITEMS = SECTIONS.flatMap((s) => s.items.map((i) => ({ ...i, section: s })));

function Sidebar({ collapsed, onToggle }) {
  return (
    <Box
      component="aside"
      sx={{
        width: collapsed ? COLLAPSED : EXPANDED,
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        color: '#F6F4F5',
        background: 'linear-gradient(170deg, #2A2C2E 0%, #36393B 50%, #4A4E51 100%)',
        boxShadow: '12px 0 40px -24px rgba(34,36,38,0.8)',
        transition: 'width 0.35s cubic-bezier(0.2, 0.7, 0.2, 1)',
        overflow: 'hidden',
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent={collapsed ? 'center' : 'space-between'} sx={{ px: 2, pt: 2.5, pb: 1.5 }}>
        <Stack direction="row" alignItems="center" spacing={1.25} sx={{ minWidth: 0 }}>
          <Box
            sx={{
              width: 42, height: 42, borderRadius: 3, flexShrink: 0,
              display: 'grid', placeItems: 'center',
              background: 'linear-gradient(135deg, #A5D8FF, #C49799)',
              boxShadow: '0 10px 20px -10px rgba(165,216,255,0.9)',
            }}
          >
            <FlightOutlined sx={{ color: '#36393B' }} />
          </Box>
          {!collapsed && (
            <Box sx={{ minWidth: 0 }}>
              <Typography fontWeight={800} color="#FFFFFF" lineHeight={1.1} noWrap>AeroComply</Typography>
              <Typography variant="caption" sx={{ color: '#BFB6BB' }} noWrap>Regulatory operations</Typography>
            </Box>
          )}
        </Stack>
        {!collapsed && (
          <IconButton onClick={onToggle} size="small" aria-label="Collapse menu" sx={{ color: '#BFB6BB', bgcolor: 'rgba(255,255,255,0.06)' }}>
            <ChevronLeft />
          </IconButton>
        )}
      </Stack>
      {collapsed && (
        <IconButton onClick={onToggle} size="small" aria-label="Expand menu" sx={{ mx: 'auto', color: '#BFB6BB', bgcolor: 'rgba(255,255,255,0.06)', mb: 1 }}>
          <ChevronRight />
        </IconButton>
      )}

      <Box sx={{ flexGrow: 1, overflowY: 'auto', overflowX: 'hidden', px: 1.25, pb: 2 }}>
        {SECTIONS.map((section) => (
          <Box key={section.label} sx={{ mb: 1.5 }}>
            {!collapsed ? (
              <Stack direction="row" alignItems="center" spacing={1} sx={{ px: 1.25, py: 0.75 }}>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: section.color, boxShadow: `0 0 10px ${section.color}` }} />
                <Typography variant="caption" sx={{ color: '#AFD0D6', letterSpacing: '0.14em', fontWeight: 700 }}>
                  {section.label.toUpperCase()}
                </Typography>
              </Stack>
            ) : (
              <Box sx={{ height: 1, bgcolor: 'rgba(255,255,255,0.1)', mx: 1.5, my: 1 }} />
            )}

            {section.items.map((item) => {
              const Icon = item.icon;
              const link = (
                <Box
                  key={item.to}
                  component={NavLink}
                  to={item.to}
                  end={item.to === '/'}
                  className="nav-item"
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    px: collapsed ? 0 : 1.25,
                    py: 0.9,
                    mb: 0.5,
                    mx: collapsed ? 'auto' : 0,
                    width: collapsed ? 52 : '100%',
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    borderRadius: 3,
                    color: '#D9D3D7',
                    textDecoration: 'none',
                    position: 'relative',
                    transition: 'background 0.3s ease, color 0.3s ease, transform 0.3s ease',
                    '&:hover': { bgcolor: 'rgba(255,255,255,0.08)', color: '#FFFFFF', transform: collapsed ? 'none' : 'translateX(3px)' },
                    '&.active': {
                      color: '#36393B',
                      background: `linear-gradient(120deg, ${section.color}, ${section.color}99)`,
                      boxShadow: `0 10px 24px -14px ${section.color}`,
                    },
                    '&.active::before': {
                      content: '""',
                      position: 'absolute',
                      left: -10,
                      top: '22%',
                      height: '56%',
                      width: 4,
                      borderRadius: 4,
                      background: '#A5D8FF',
                      boxShadow: '0 0 12px #A5D8FF',
                      display: collapsed ? 'none' : 'block',
                    },
                  }}
                >
                  <Box
                    className="nav-icon"
                    sx={{
                      width: 34, height: 34, borderRadius: 2.5, flexShrink: 0,
                      display: 'grid', placeItems: 'center',
                      bgcolor: `${section.color}33`,
                      color: 'inherit',
                    }}
                  >
                    <Icon sx={{ fontSize: 19 }} />
                  </Box>
                  {!collapsed && (
                    <Typography variant="body2" fontWeight={600} noWrap>{item.text}</Typography>
                  )}
                </Box>
              );
              return collapsed ? (
                <Tooltip key={item.to} title={item.text} placement="right" arrow>
                  {link}
                </Tooltip>
              ) : (
                link
              );
            })}
          </Box>
        ))}
      </Box>

      {!collapsed && (
        <Box sx={{ m: 1.5, p: 1.5, borderRadius: 3, bgcolor: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)' }}>
          <Typography variant="caption" sx={{ color: '#BFB6BB' }}>Demo workspace</Typography>
          <Typography variant="body2" color="#FFFFFF" fontWeight={600}>Dummy data active</Typography>
        </Box>
      )}
    </Box>
  );
}

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const { pathname } = useLocation();

  const current = ALL_ITEMS.find((i) => (i.to === '/' ? pathname === '/' : pathname.startsWith(i.to)));

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          spacing={2}
          sx={{
            position: 'sticky',
            top: 0,
            zIndex: 5,
            px: { xs: 2, md: 4 },
            py: 1.5,
            backdropFilter: 'blur(12px)',
            bgcolor: 'rgba(246,244,245,0.78)',
            borderBottom: '1px solid rgba(191,182,187,0.4)',
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" noWrap>
              AeroComply / {current?.section.label ?? 'Workspace'}
            </Typography>
            <Typography fontWeight={700} noWrap>{current?.text ?? 'Workspace'}</Typography>
          </Box>
          <Stack direction="row" alignItems="center" spacing={2}>
            <TextField
              size="small"
              placeholder="Search regulations, gaps, policies"
              sx={{
                width: { xs: 0, md: 280 },
                display: { xs: 'none', md: 'block' },
                '& .MuiOutlinedInput-root': { borderRadius: 999, bgcolor: '#FFFFFF' },
              }}
              slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchOutlined fontSize="small" /></InputAdornment> } }}
            />
            <Stack direction="row" alignItems="center" spacing={1}>
              <Avatar sx={{ width: 36, height: 36, bgcolor: '#8E8590', color: '#FFFFFF', fontSize: 14, fontWeight: 700 }}>CO</Avatar>
              <Box sx={{ display: { xs: 'none', lg: 'block' } }}>
                <Typography variant="body2" fontWeight={700} lineHeight={1.1}>Compliance Officer</Typography>
                <Typography variant="caption" color="text.secondary">Demo user</Typography>
              </Box>
            </Stack>
          </Stack>
        </Stack>

        <Box key={pathname} className="page-enter" sx={{ px: { xs: 2, md: 4 }, py: 3, pb: 12 }}>
          <Outlet />
        </Box>
      </Box>

      <Fab
        variant="extended"
        onClick={() => setChatOpen(true)}
        sx={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          color: '#FFFFFF',
          background: 'linear-gradient(135deg, #4A4E51, #36393B)',
          boxShadow: '0 16px 30px -12px rgba(54,57,59,0.7), 0 0 0 4px rgba(165,216,255,0.35)',
          '&:hover': { background: 'linear-gradient(135deg, #5A5F62, #2A2C2E)', transform: 'translateY(-2px)' },
          transition: 'transform 0.25s ease',
        }}
      >
        <ChatOutlined sx={{ mr: 1 }} />
        Ask AeroComply AI
      </Fab>

      <Drawer
        anchor="right"
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        slotProps={{ paper: { sx: { width: 420, bgcolor: '#F6F4F5', backgroundImage: 'none' } } }}
      >
        <CopilotPanel onClose={() => setChatOpen(false)} />
      </Drawer>
    </Box>
  );
}
