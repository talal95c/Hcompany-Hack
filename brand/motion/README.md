# Rio — logo motion

Animation ultra minimaliste du R (Remotion, 60 fps, 4 s) : tracé fin du corps, remplissage en balayage à 45°, la jambe glisse le long de sa propre pente et s'emboîte.

| Composition | Format | Rendu |
| --- | --- | --- |
| `LogoDark` | 1920×1080, blanc sur noir | `renders/LogoDark.mp4` |
| `LogoLight` | 1920×1080, noir sur blanc | `renders/LogoLight.mp4` |
| `LogoSquare` | 1080×1080, blanc sur noir | `renders/LogoSquare.mp4` |
| `AppIcon` | 1080×1080, icône d'app | `renders/AppIcon.mp4` |

```bash
npm install
npm run dev                                          # Remotion Studio
npx remotion render src/index.ts LogoDark out/LogoDark.mp4 --crf=12
```
