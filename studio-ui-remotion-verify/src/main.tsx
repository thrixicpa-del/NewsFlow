import { createRoot } from 'react-dom/client';
import { App } from './ui/App';
import './ui/styles.css';
import './ui/layout/app-shell-responsive.css';

createRoot(document.getElementById('root')!).render(<App />);
