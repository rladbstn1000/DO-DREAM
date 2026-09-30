import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { ShowcaseApp, type ShowcasePort } from './App';
import { samples, findSample } from './samples';
import { createShowcaseStore, type StorageLike } from './store';
import '../student/student.css';
import './showcase.css';

// This entry explicitly selects the public sample port. No live/auth adapter is imported.
let storage: StorageLike | undefined;
try { storage = window.sessionStorage; } catch { /* The store explains its memory-only mode. */ }
const port: ShowcasePort = { samples, findSample, store: createShowcaseStore(storage) };
createRoot(document.getElementById('root')!).render(<HashRouter><ShowcaseApp port={port} /></HashRouter>);
