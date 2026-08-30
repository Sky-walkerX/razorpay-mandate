import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** shadcn's class combiner: conditional classes in, conflicts resolved out. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
