#ifndef SIGLUM_PREVIEW_H
#define SIGLUM_PREVIEW_H
extern int siglum_preview_is_paused;
extern int siglum_preview_loop_done;
extern int siglum_checkpoint_is_paused;
int siglum_preview_poll(void);
int siglum_preview_after_maincontrol(void);
int siglum_preview_enter_continue(void);
int siglum_preview_enter_next(int page);
void siglum_preview_resource_event(int event);
#endif
