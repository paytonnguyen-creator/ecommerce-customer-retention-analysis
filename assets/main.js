/* Shared by index.html and the case study pages. Every block below is guarded,
   because the case study pages have a nav but no hero, typewriter, or sections. */

const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

const nav = document.getElementById('nav');
const links = [...document.querySelectorAll('.nav nav a')];

/* Nav goes solid once the hero is behind us. Pages without a hero stay solid. */
const hero = document.querySelector('.hero');
if (nav && hero) {
  const onScroll = () => nav.classList.toggle('is-solid', window.scrollY > window.innerHeight * 0.72);
  onScroll();
  addEventListener('scroll', onScroll, { passive: true });
}

/* Mobile menu */
const toggle = document.querySelector('.nav-toggle');
if (nav && toggle) {
  toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
  });
  links.forEach(a => a.addEventListener('click', () => {
    nav.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
  }));
}

/* Highlight the section you're looking at. Only same-page "#id" links qualify —
   the case study nav points at index.html#id, which isn't a valid selector. */
const spySections = links
  .map(a => {
    const href = a.getAttribute('href') || '';
    return href.startsWith('#') && href.length > 1 ? document.querySelector(href) : null;
  })
  .filter(Boolean);

if (spySections.length) {
  const spy = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      links.forEach(a => a.classList.toggle('is-active', a.getAttribute('href') === '#' + e.target.id));
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  spySections.forEach(s => spy.observe(s));
}

/* Typewriter. Under reduced-motion it just shows the first line. */
const typed = document.getElementById('typed');
if (typed) {
  const lines = [
    'Welcome.',
    'Cognitive science meets data.',
    'Analysis that ends in a decision.',
  ];

  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    typed.textContent = lines[0];
  } else {
    let li = 0, ci = 0, deleting = false;
    const tick = () => {
      const line = lines[li];
      ci += deleting ? -1 : 1;
      typed.textContent = line.slice(0, ci);

      let wait = deleting ? 40 : 75;
      if (!deleting && ci === line.length) { deleting = true; wait = 2100; }
      // short blank gap — a long one reads as a broken/empty hero
      else if (deleting && ci === 0) { deleting = false; li = (li + 1) % lines.length; wait = 180; }
      setTimeout(tick, wait);
    };
    tick();
  }
}
