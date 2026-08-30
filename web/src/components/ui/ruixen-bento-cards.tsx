import React from 'react';
import { cn } from '@/lib/utils';

export interface BentoCardProps {
  className?: string;
  title: string;
  description: string;
  tag?: string;
  bound?: string;
  children?: React.ReactNode;
}

export const PlusIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    width={24}
    height={24}
    strokeWidth="1.2"
    stroke="currentColor"
    aria-hidden="true"
    className={cn('size-4 text-zinc-400 dark:text-zinc-500 pointer-events-none select-none', className)}
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" />
  </svg>
);

export const CornerPlusIcons = () => (
  <>
    <PlusIcon className="absolute -top-2 -left-2 z-20" />
    <PlusIcon className="absolute -top-2 -right-2 z-20" />
    <PlusIcon className="absolute -bottom-2 -left-2 z-20" />
    <PlusIcon className="absolute -bottom-2 -right-2 z-20" />
  </>
);

export const PlusCard: React.FC<BentoCardProps> = ({
  className = '',
  title,
  description,
  tag,
  bound,
  children,
}) => {
  return (
    <div
      className={cn(
        'group relative rounded-lg border border-dashed border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-950/60 p-6 backdrop-blur-xs transition-all duration-200 hover:border-zinc-400 hover:bg-white dark:hover:border-zinc-600 dark:hover:bg-zinc-900/80 min-h-[160px] flex flex-col justify-between',
        className
      )}
    >
      <CornerPlusIcons />
      <div className="relative z-10 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-base font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
            {title}
          </h3>
          {tag && (
            <span className="rounded border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
              {tag}
            </span>
          )}
        </div>
        <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{description}</p>
        {bound && (
          <div className="mt-3 font-mono text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {bound}
          </div>
        )}
        {children}
      </div>
    </div>
  );
};

export default function RuixenBentoCards() {
  const cardContents = [
    {
      title: 'Beautiful Components',
      description:
        'Ruixen UI provides stunning, ready-made components built with consistent design and performance in mind.',
    },
    {
      title: 'Developer Friendly',
      description:
        'Simple APIs and excellent documentation make it easy to integrate and customize Ruixen UI in your apps.',
    },
    {
      title: 'Flexible Layouts',
      description:
        'Design dynamic, responsive layouts using grid utilities and composable layout primitives that scale across all viewports.',
    },
    {
      title: 'Dark Mode Support',
      description:
        'Every component is thoughtfully designed to work seamlessly in both light and dark themes.',
    },
    {
      title: 'Fast & Lightweight',
      description:
        'Built for speed and performance, ensuring sub-millisecond execution and minimal bundle footprint.',
    },
  ];

  return (
    <section className="relative overflow-hidden border-y border-zinc-200 bg-zinc-50/50 py-12 dark:border-zinc-800 dark:bg-zinc-950/30">
      <div className="container mx-auto px-4">
        {/* Responsive Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 auto-rows-auto gap-4">
          <PlusCard {...cardContents[0]} className="lg:col-span-3 lg:row-span-2" />
          <PlusCard {...cardContents[1]} className="lg:col-span-2 lg:row-span-2" />
          <PlusCard {...cardContents[2]} className="lg:col-span-4 lg:row-span-1" />
          <PlusCard {...cardContents[3]} className="lg:col-span-2 lg:row-span-1" />
          <PlusCard {...cardContents[4]} className="lg:col-span-2 lg:row-span-1" />
        </div>

        {/* Section Footer Heading */}
        <div className="ml-auto mt-8 max-w-2xl text-right">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 md:text-5xl">
            Built for performance. Designed for flexibility.
          </h2>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400 md:text-base">
            Ruixen UI gives you the tools to build beautiful, high-performing websites with lightning speed.
          </p>
        </div>
      </div>
    </section>
  );
}

