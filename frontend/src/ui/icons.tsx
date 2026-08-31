import React from 'react'

type IconProps = React.SVGProps<SVGSVGElement>

function IconBase({ children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {children}
    </svg>
  )
}

export const HomeIcon = (props: IconProps) => <IconBase {...props}><path d="M3.5 10.5 12 3.8l8.5 6.7" /><path d="M5.5 9.5v10h13v-10" /><path d="M9.5 19.5v-6h5v6" /></IconBase>
export const PrepareIcon = (props: IconProps) => <IconBase {...props}><path d="M4 6.5h16" /><path d="M7 3.5v6" /><path d="M17 3.5v6" /><rect x="4" y="5" width="16" height="15" rx="2" /><path d="m8.5 14 2 2 5-5" /></IconBase>
export const SendIcon = (props: IconProps) => <IconBase {...props}><path d="m4 4 16 8-16 8 3-8-3-8Z" /><path d="M7 12h13" /></IconBase>
export const RunIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="m10 8 6 4-6 4V8Z" /></IconBase>
export const ReviewIcon = (props: IconProps) => <IconBase {...props}><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /><path d="M8 11h6" /><path d="M11 8v6" /></IconBase>
export const SettingsIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.5 1a7 7 0 0 0-1.8-1L14.2 3h-4.4l-.4 3a7 7 0 0 0-1.8 1l-2.5-1-2 3.4L5.1 11a7 7 0 0 0 0 2l-2 1.6 2 3.4 2.5-1a7 7 0 0 0 1.8 1l.4 3h4.4l.4-3a7 7 0 0 0 1.8-1l2.5 1 2-3.4-2-1.6c.1-.3.1-.7.1-1Z" /></IconBase>
export const SearchIcon = (props: IconProps) => <IconBase {...props}><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /></IconBase>
export const PlusIcon = (props: IconProps) => <IconBase {...props}><path d="M12 5v14" /><path d="M5 12h14" /></IconBase>
export const ChevronRightIcon = (props: IconProps) => <IconBase {...props}><path d="m9 5 7 7-7 7" /></IconBase>
export const AlertIcon = (props: IconProps) => <IconBase {...props}><path d="M12 4 2.8 20h18.4L12 4Z" /><path d="M12 9v5" /><path d="M12 17.5h.01" /></IconBase>
export const CheckIcon = (props: IconProps) => <IconBase {...props}><path d="m5 12 4 4L19 6" /></IconBase>
export const ClockIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></IconBase>
export const BrowserIcon = (props: IconProps) => <IconBase {...props}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 8h18" /><path d="M7 6h.01" /><path d="M10 6h.01" /></IconBase>
export const NetworkIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="M3.5 9h17" /><path d="M3.5 15h17" /><path d="M12 3a15 15 0 0 1 0 18" /><path d="M12 3a15 15 0 0 0 0 18" /></IconBase>
export const AccountIcon = (props: IconProps) => <IconBase {...props}><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.7-4 3-6 7-6s6.3 2 7 6" /></IconBase>
export const AssetIcon = (props: IconProps) => <IconBase {...props}><rect x="4" y="4" width="16" height="16" rx="2" /><circle cx="9" cy="9" r="1.5" /><path d="m6 17 4-4 3 3 2-2 3 3" /></IconBase>
export const FlowIcon = (props: IconProps) => <IconBase {...props}><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="M8 6h8" /><path d="m7 7.5 4 8.5" /><path d="m17 7.5-4 8.5" /></IconBase>
