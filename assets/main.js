const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

const nav = document.querySelector('.nav');
if (nav) {
  const onScroll = () => nav.classList.toggle('is-stuck', window.scrollY > 8);
  onScroll();
  addEventListener('scroll', onScroll, { passive: true });
}
