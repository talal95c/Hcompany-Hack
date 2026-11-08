import {copyFile} from 'node:fs/promises';
await copyFile(new URL('../out/single/index.html',import.meta.url),new URL('../out/rio-pitch.html',import.meta.url));
