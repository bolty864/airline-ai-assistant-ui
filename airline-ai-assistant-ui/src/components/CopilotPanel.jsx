import { useState } from 'react';
import { Box, Button, Chip, Divider, IconButton, Paper, Stack, TextField, Typography } from '@mui/material';
import { CloseOutlined, SendOutlined } from '@mui/icons-material';
import { askCopilot, copilotSuggestions } from '../data/mock.js';

export default function CopilotPanel({ fullPage = false, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: 'ai',
      text: 'Ask about regulations, obligations, gaps or policies. Answers are grounded only on approved policies and regulator documents, with citations.',
      sources: [],
    },
  ]);
  const [input, setInput] = useState('');

  const send = (question) => {
    const text = (question ?? input).trim();
    if (!text) return;
    const reply = askCopilot(text);
    setMessages((prev) => [...prev, { role: 'user', text }, { role: 'ai', ...reply }]);
    setInput('');
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: fullPage ? 'calc(100vh - 140px)' : '100%', p: 2 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="h6" fontWeight={700}>Ask AeroComply AI</Typography>
        {onClose && (
          <IconButton onClick={onClose} aria-label="Close copilot">
            <CloseOutlined />
          </IconButton>
        )}
      </Stack>

      <Box sx={{ flexGrow: 1, overflowY: 'auto', pr: 1 }}>
        <Stack spacing={1.5}>
          {messages.map((m, i) => (
            <Paper
              key={i}
              variant="outlined"
              sx={{ p: 1.5, bgcolor: m.role === 'user' ? '#E6F4FA' : '#FFFFFF', ml: m.role === 'user' ? 6 : 0, mr: m.role === 'user' ? 0 : 4 }}
            >
              <Typography variant="body2">{m.text}</Typography>
              {m.sources?.length > 0 && (
                <>
                  <Divider sx={{ my: 1 }} />
                  <Typography variant="caption" color="text.secondary">Sources</Typography>
                  <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" mt={0.5}>
                    {m.sources.map((s) => <Chip key={s} size="small" label={s} />)}
                  </Stack>
                </>
              )}
            </Paper>
          ))}
        </Stack>
      </Box>

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" my={1}>
        {copilotSuggestions.map((s) => (
          <Chip key={s} label={s} size="small" onClick={() => send(s)} />
        ))}
      </Stack>

      <Stack direction="row" spacing={1}>
        <TextField
          fullWidth
          size="small"
          placeholder="Ask a compliance question"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
        />
        <Button variant="contained" onClick={() => send()} aria-label="Send question">
          <SendOutlined />
        </Button>
      </Stack>
    </Box>
  );
}
