/** Plain-language notes for the quality flags the API reports on a workout. */
export function qualityNotes(flags: Record<string, number>, issues: string[]): string[] {
  const notes: string[] = []
  for (const [key, n] of Object.entries(flags)) {
    if (!n) continue
    if (key === 'hr_samples_dropped') notes.push(`${n} heart-rate ${n === 1 ? 'reading was' : 'readings were'} left out because ${n === 1 ? 'it' : 'they'} looked off. Check this reading before you lean on heart-rate figures.`)
    else if (key === 'route_points_dropped') notes.push(`${n} route ${n === 1 ? 'point was' : 'points were'} left out because ${n === 1 ? 'it' : 'they'} looked off. The route may have small gaps.`)
    else if (key.startsWith('unit_')) notes.push(`${n} ${key.slice(5).replace(/_/g, ' ')} ${n === 1 ? 'value arrived' : 'values arrived'} in an unexpected unit and ${n === 1 ? 'was' : 'were'} converted.`)
    else notes.push(`${key.replace(/_/g, ' ')}: ${n}.`)
  }
  for (const i of issues) notes.push(i.endsWith('.') ? i : `${i}.`)
  return notes
}
