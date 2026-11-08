import QRCode from 'qrcode';
import {writeFile} from 'node:fs/promises';
await writeFile(new URL('../public/qr.svg', import.meta.url), await QRCode.toString('https://rio.vignemale.com', {type:'svg', margin:2, color:{dark:'#1a1a1a',light:'#ffffff'}}));
