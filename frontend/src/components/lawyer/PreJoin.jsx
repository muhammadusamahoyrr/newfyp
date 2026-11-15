'use client';
/* The lawyer's join screen: the shared one, with the lawyer's chat panel for
 * "Message" (before and during the call) and their own-link field. */
import { PreJoinModal as SharedPreJoin } from "@/components/shared/PreJoin.jsx";
import { useChatDock } from "./ChatDock.jsx";

export function PreJoinModal(props) {
    const dock = useChatDock();
    const { apt } = props;
    const openChat = dock ? () => dock.openChat({ id: apt.id, client: apt.client, at: apt.at }) : null;
    return <SharedPreJoin {...props} onMessage={openChat} onOpenChatInCall={openChat} />;
}
