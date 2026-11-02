'use client';
import { useEffect, useId, useRef, useState } from 'react';
type Department = { id: number; name: string };

export function DepartmentPicker({ run, initialName = '', onChange }: { run: string; initialName?: string; onChange: (id: string, name?: string) => void }) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [query,setQuery] = useState(initialName);
  const [open,setOpen] = useState(false);
  const [options,setOptions] = useState<Department[]>([]);
  const [active,setActive] = useState(-1);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState('');
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);setError('');
      try {
        const response = await fetch(`/api/departments?run=${encodeURIComponent(run)}&q=${encodeURIComponent(query)}`, { signal:controller.signal });
        if (!response.ok) throw new Error('Department names could not be loaded. Try again.');
        const result = await response.json();setOptions(result.departments);setActive(-1);
      } catch(error) { if(!controller.signal.aborted){setOptions([]);setError(error instanceof Error?error.message:'Unable to load departments.');} }
      finally { if(!controller.signal.aborted)setLoading(false); }
    },150);
    return () => { clearTimeout(timer);controller.abort(); };
  },[run,query,open]);
  function select(department: Department | null) {
    setQuery(department?.name || '');onChange(department?String(department.id):'', department?.name || '');setOpen(false);setActive(-1);input.current?.setCustomValidity('');
  }
  return <div className="department-picker">
    <label htmlFor={id}>Department name</label>
    <div className="department-input"><input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} value={query} placeholder="Search department names" autoComplete="off" maxLength={100}
      onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)}
      onChange={event=>{setQuery(event.target.value);setOptions([]);setActive(-1);setOpen(true);onChange('');event.target.setCustomValidity(event.target.value.trim()?'Choose a department from the matching names, or clear to include all departments.':'');}}
      onKeyDown={event=>{if(event.key==='Escape')setOpen(false);if(event.key==='ArrowDown'){event.preventDefault();setOpen(true);setActive(value=>Math.min(value+1,options.length-1));}if(event.key==='ArrowUp'){event.preventDefault();setActive(value=>Math.max(value-1,0));}if(event.key==='Enter'&&open&&active>=0&&options[active]){event.preventDefault();select(options[active]);}}}/>
      {query&&<button type="button" className="department-clear" aria-label="Clear department" onClick={()=>select(null)}>×</button>}
    </div>
    {open&&<div className="department-options"><button type="button" className="all-departments" onMouseDown={event=>event.preventDefault()} onClick={()=>select(null)}>All departments</button>
      <div id={`${id}-options`} role="listbox" aria-label="Matching department names">{options.map((department,index)=><button type="button" role="option" id={`${id}-${index}`} aria-selected={active===index} key={department.id} onMouseDown={event=>event.preventDefault()} onClick={()=>select(department)}><span>{department.name}</span><small>ID {department.id}</small></button>)}</div>
      <p role="status">{loading?'Searching departments…':error||(!options.length?'No matching departments.':'Type a name to narrow the results.')}</p>
    </div>}
  </div>;
}
